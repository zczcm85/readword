import streamlit as st
from gtts import gTTS
from pydub import AudioSegment
import os
from datetime import datetime
from googletrans import Translator
from io import BytesIO

# --- Configuration Defaults ---
DEFAULT_REPEAT_COUNT = 2
DEFAULT_WORDS_PER_FILE = 10
DEFAULT_SLOW_SPEED = False
DEFAULT_SPELL_PAUSE_MS = 20
DEFAULT_WORD_PAUSE_MS = 300
OUTPUT_DIR = "audio_output"

# --- Initialization ---
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

# --- Helper Functions ---

@st.cache_resource
def get_translator():
    """初始化翻译器并缓存，避免重复创建"""
    return Translator()

def create_audio_segment(text, lang='en', slow=False):
    """使用gTTS生成文本的音频片段，直接在内存中处理"""
    try:
        # 确保输入是字符串
        tts = gTTS(text=str(text), lang=lang, slow=slow)
        fp = BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return AudioSegment.from_file(fp, format="mp3")
    except Exception as e:
        print(f"Error creating audio for {text}: {e}")
        # 出错时返回500ms静音，防止程序崩溃
        return AudioSegment.silent(duration=500)

def generate_word_audio(word, translation, repeat_count, slow_speed, spell_pause_ms, word_pause_ms):
    """生成单个单词的完整听写音频片段"""
    
    # 1. 生成正常速度和慢速的单词音频
    full_word_audio_normal = create_audio_segment(word, slow=False)
    full_word_audio_slow = create_audio_segment(word, slow=True)

    # 2. 生成拼读音频 (S-P-E-L-L)
    spelling_audio_segments = []
    # 过滤掉非字母字符，只拼读字母
    clean_word = ''.join(filter(str.isalpha, word))
    
    for char in clean_word:
        char_audio = create_audio_segment(char, slow=False)
        spelling_audio_segments.append(char_audio)
        spelling_audio_segments.append(AudioSegment.silent(duration=spell_pause_ms))

    spelling_combined = AudioSegment.empty()
    if spelling_audio_segments:
        # 去掉最后一个多余的停顿
        spelling_combined = sum(spelling_audio_segments[:-1])

    # 3. 组合音频
    word_final_audio = AudioSegment.empty()

    # A. 重复朗读单词
    for _ in range(repeat_count):
        word_final_audio += full_word_audio_normal if not slow_speed else full_word_audio_slow
    
    # B. 停顿 -> 拼读 -> 停顿
    word_final_audio += AudioSegment.silent(duration=word_pause_ms)
    word_final_audio += spelling_combined
    word_final_audio += AudioSegment.silent(duration=word_pause_ms)
    
    # C. 再次朗读单词
    word_final_audio += full_word_audio_normal if not slow_speed else full_word_audio_slow
    word_final_audio += AudioSegment.silent(duration=word_pause_ms)

    # D. 中文翻译 (如果有)
    if translation:
        # 使用 zh 生成中文语音
        chinese_audio = create_audio_segment(translation, lang='zh', slow=False)
        word_final_audio += chinese_audio

    # E. 单词间的大停顿
    word_final_audio += AudioSegment.silent(duration=word_pause_ms * 2)

    return word_final_audio

# --- Main Application ---

def main_app():
    st.set_page_config(layout="wide", page_title="听写音频生成器")
    st.title("📝 听写音频生成器")

    st.markdown("""
    这个应用可以帮助你根据单词列表生成听写音频。
    支持 **上传文件** 或 **直接粘贴文本**。
    """)

    # --- 侧边栏配置 ---
    st.sidebar.header("⚙️ 配置项")
    repeat_count = st.sidebar.number_input("每个单词朗读次数", min_value=1, max_value=5, value=DEFAULT_REPEAT_COUNT)
    words_per_file = st.sidebar.number_input("处理单词总数 (0表示所有单词)", min_value=0, value=DEFAULT_WORDS_PER_FILE)
    slow_speed = st.sidebar.checkbox("慢速朗读", value=DEFAULT_SLOW_SPEED)
    spell_pause_ms = st.sidebar.slider("拼读字母间停顿 (毫秒)", min_value=0, max_value=500, value=DEFAULT_SPELL_PAUSE_MS)
    word_pause_ms = st.sidebar.slider("单词朗读与拼读间停顿 (毫秒)", min_value=0, max_value=1000, value=DEFAULT_WORD_PAUSE_MS)

    # --- 输入方式处理 ---
    temp_word_file_path = os.path.join("/tmp", "process_list.txt")
    has_valid_input = False
    source_name = "input_words"

    # 创建 Tab
    tab1, tab2 = st.tabs(["📂 上传文件 (txt)", "✍️ 直接输入文本"])

    uploaded_file = None # 初始化变量

    with tab1:
        uploaded_file = st.file_uploader("选择 word.txt 文件", type=["txt"])
        if uploaded_file is not None:
            # 如果上传了文件，写入临时文件
            with open(temp_word_file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            has_valid_input = True
            source_name = uploaded_file.name
            st.success(f"已加载文件: {uploaded_file.name}")

    with tab2:
        user_text = st.text_area(
            "在此输入或粘贴单词列表 (每行一个，格式：'单词' 或 '单词,中文')", 
            height=200,
            placeholder="例如：\nApple\nBanana,香蕉\nOrange"
        )
        if user_text.strip():
            # 逻辑：如果没有上传文件，或者虽然上传了但用户想用文本覆盖，则优先使用文本
            # 但为了避免混淆，如果同时存在，我们在下面提示
            if not uploaded_file: 
                with open(temp_word_file_path, "w", encoding="utf-8") as f:
                    f.write(user_text)
                has_valid_input = True
                source_name = "手动输入列表.txt"
                st.success("已加载手动输入的文本")
            elif uploaded_file:
                st.info("⚠️ 检测到您同时上传了文件，系统将优先处理上传的文件。如需处理文本框内容，请先移除上传的文件。")

    # --- 处理逻辑 ---
    if has_valid_input:
        st.divider()
        if st.button("🎵 开始生成音频", type="primary"):
            st.info(f"正在处理来源: {source_name}...请稍候。")
            
            words_to_translate = []
            ordered_words_data = []
            
            # 1. 读取文件
            try:
                with open(temp_word_file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        stripped_line = line.strip()
                        if not stripped_line:
                            continue
                        # 兼容中文逗号
                        stripped_line = stripped_line.replace('，', ',')
                        parts = stripped_line.split(',', 1)
                        english_word = parts[0].strip()
                        chinese_translation = parts[1].strip() if len(parts) > 1 else ''

                        if not chinese_translation:
                            words_to_translate.append(english_word)
                        ordered_words_data.append((english_word, chinese_translation))
            except Exception as e:
                st.error(f"读取数据错误: {e}")
                return

            # 2. 翻译缺失的单词
            newly_translated_words = []
            if words_to_translate:
                # 这里调用了之前丢失的 get_translator 函数
                translator = get_translator()
                status_bar = st.progress(0)
                st.write(f"正在翻译 {len(words_to_translate)} 个单词...")
                
                for i, word in enumerate(words_to_translate):
                    try:
                        # 使用 zh-CN 或 zh 提高成功率
                        translation = translator.translate(word, src='en', dest='zh-CN')
                        text_result = translation.text
                        newly_translated_words.append((word, text_result))
                    except Exception as e:
                        # 备选重试
                        try:
                            translation = translator.translate(word, src='en', dest='zh')
                            newly_translated_words.append((word, translation.text))
                        except:
                            st.warning(f"翻译 '{word}' 失败，将跳过中文朗读。")
                            newly_translated_words.append((word, ""))
                    
                    status_bar.progress((i + 1) / len(words_to_translate))
                
                st.success("翻译处理完成！")

            # 3. 合并数据
            final_words_dict = {word: translation for word, translation in ordered_words_data}
            for word_en, word_zh in newly_translated_words:
                final_words_dict[word_en] = word_zh

            # 准备生成音频的数据
            words_data_for_audio = []
            for word, _ in ordered_words_data:
                words_data_for_audio.append((word, final_words_dict.get(word, "")))

            # 4. 生成音频
            if not words_data_for_audio:
                st.warning("没有有效的单词数据。")
                return

            limit = words_per_file if words_per_file > 0 else len(words_data_for_audio)
            words_to_process = words_data_for_audio[:limit]
            
            st.write(f"正在为 {len(words_to_process)} 个单词生成音频...")
            
            combined_audio_segment = AudioSegment.empty()
            audio_progress = st.progress(0)
            status_text = st.empty()

            for i, (word, translation) in enumerate(words_to_process):
                display_trans = f"({translation})" if translation else ""
                status_text.text(f"正在生成: {word} {display_trans} ({i+1}/{len(words_to_process)})")
                
                try:
                    word_audio = generate_word_audio(
                        word, translation, repeat_count, slow_speed, 
                        spell_pause_ms, word_pause_ms
                    )
                    combined_audio_segment += word_audio
                except Exception as e:
                    st.error(f"生成 '{word}' 音频失败: {e}")
                
                audio_progress.progress((i + 1) / len(words_to_process))

            # 5. 导出结果
            if len(combined_audio_segment) > 0:
                timestamp = datetime.now().strftime("%y%m%d-%H%M%S")
                audio_buffer = BytesIO()
                combined_audio_segment.export(audio_buffer, format="mp3")
                audio_buffer.seek(0)
                
                st.success("🎉 音频生成成功！")
                st.audio(audio_buffer, format='audio/mp3')
                
                st.download_button(
                    label="⬇️ 下载 MP3 音频",
                    data=audio_buffer,
                    file_name=f"dictation_{timestamp}.mp3",
                    mime="audio/mp3"
                )
            else:
                st.error("未能生成任何音频数据。")
    
    else:
        st.info("👈 请在上方选项卡中 [上传文件] 或 [输入单词列表] 以开始。")

if __name__ == "__main__":
    main_app()
