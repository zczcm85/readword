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
    """初始化翻译器并缓存"""
    return Translator()

def create_audio_segment(text, lang='en', slow=False):
    """使用gTTS生成文本的音频片段"""
    try:
        tts = gTTS(text=str(text), lang=lang, slow=slow)
        fp = BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return AudioSegment.from_file(fp, format="mp3")
    except Exception as e:
        print(f"Error creating audio for {text}: {e}")
        return AudioSegment.silent(duration=500)

def generate_word_audio(word, translation, repeat_count, slow_speed, spell_pause_ms, word_pause_ms):
    """生成单个单词的完整听写音频片段"""
    full_word_audio_normal = create_audio_segment(word, slow=False)
    full_word_audio_slow = create_audio_segment(word, slow=True)

    spelling_audio_segments = []
    clean_word = ''.join(filter(str.isalpha, word))
    
    for char in clean_word:
        char_audio = create_audio_segment(char, slow=False)
        spelling_audio_segments.append(char_audio)
        spelling_audio_segments.append(AudioSegment.silent(duration=spell_pause_ms))

    spelling_combined = AudioSegment.empty()
    if spelling_audio_segments:
        spelling_combined = sum(spelling_audio_segments[:-1])

    word_final_audio = AudioSegment.empty()
    for _ in range(repeat_count):
        word_final_audio += full_word_audio_normal if not slow_speed else full_word_audio_slow
    
    word_final_audio += AudioSegment.silent(duration=word_pause_ms)
    word_final_audio += spelling_combined
    word_final_audio += AudioSegment.silent(duration=word_pause_ms)
    
    word_final_audio += full_word_audio_normal if not slow_speed else full_word_audio_slow
    word_final_audio += AudioSegment.silent(duration=word_pause_ms)

    if translation:
        chinese_audio = create_audio_segment(translation, lang='zh', slow=False)
        word_final_audio += chinese_audio

    word_final_audio += AudioSegment.silent(duration=word_pause_ms * 2)

    return word_final_audio

# --- Authentication Function ---
def check_password():
    """检查密码是否正确"""
    
    # 1. 尝试从 Streamlit Secrets 获取密码，如果没有设置，默认为 '123456'
    if "PASSWORD" in st.secrets:
        secret_password = st.secrets["PASSWORD"]
    else:
        # 如果还没配置 Secrets，暂时用这个默认密码，方便用户测试
        secret_password = "123456"

    # 2. 初始化 session state
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False

    # 3. 如果已经登录成功，返回 True
    if st.session_state.password_correct:
        return True

    # 4. 显示登录界面
    st.set_page_config(page_title="登录 - 听写生成器")
    st.title("🔒 请输入访问密码")
    
    password_input = st.text_input("密码", type="password")
    
    if st.button("登录"):
        if password_input == secret_password:
            st.session_state.password_correct = True
            st.rerun()  # 刷新页面进入应用
        else:
            st.error("❌ 密码错误")

    return False

# --- Main Application Logic ---

def run_main_app():
    # 这里放原来 main_app 的所有 UI 代码，稍微改个名以示区分
    # 注意：set_page_config 只能调用一次，所以移到了 check_password 或这里的第一行，视情况而定
    # 但由于 check_password 可能先运行，set_page_config 最好放在最外层控制，或者由 check_password 处理
    
    st.title("📝 听写音频生成器")

    st.markdown("""
    这个应用可以帮助你根据单词列表生成听写音频。
    支持 **上传文件** 或 **直接粘贴文本**。
    """)

    st.sidebar.header("⚙️ 配置项")
    repeat_count = st.sidebar.number_input("每个单词朗读次数", min_value=1, max_value=5, value=DEFAULT_REPEAT_COUNT)
    words_per_file = st.sidebar.number_input("处理单词总数 (0表示所有单词)", min_value=0, value=DEFAULT_WORDS_PER_FILE)
    slow_speed = st.sidebar.checkbox("慢速朗读", value=DEFAULT_SLOW_SPEED)
    spell_pause_ms = st.sidebar.slider("拼读字母间停顿 (毫秒)", min_value=0, max_value=500, value=DEFAULT_SPELL_PAUSE_MS)
    word_pause_ms = st.sidebar.slider("单词朗读与拼读间停顿 (毫秒)", min_value=0, max_value=1000, value=DEFAULT_WORD_PAUSE_MS)

    temp_word_file_path = os.path.join("/tmp", "process_list.txt")
    has_valid_input = False
    source_name = "input_words"

    tab1, tab2 = st.tabs(["📂 上传文件 (txt)", "✍️ 直接输入文本"])
    uploaded_file = None 

    with tab1:
        uploaded_file = st.file_uploader("选择 word.txt 文件", type=["txt"])
        if uploaded_file is not None:
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
            if not uploaded_file: 
                with open(temp_word_file_path, "w", encoding="utf-8") as f:
                    f.write(user_text)
                has_valid_input = True
                source_name = "手动输入列表.txt"
                st.success("已加载手动输入的文本")
            elif uploaded_file:
                st.info("⚠️ 检测到您同时上传了文件，系统将优先处理上传的文件。")

    if has_valid_input:
        st.divider()
        if st.button("🎵 开始生成音频", type="primary"):
            st.info(f"正在处理来源: {source_name}...请稍候。")
            
            words_to_translate = []
            ordered_words_data = []
            
            try:
                with open(temp_word_file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        stripped_line = line.strip()
                        if not stripped_line:
                            continue
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

            newly_translated_words = []
            if words_to_translate:
                translator = get_translator()
                status_bar = st.progress(0)
                st.write(f"正在翻译 {len(words_to_translate)} 个单词...")
                for i, word in enumerate(words_to_translate):
                    try:
                        translation = translator.translate(word, src='en', dest='zh-CN')
                        newly_translated_words.append((word, translation.text))
                    except Exception as e:
                        try:
                            translation = translator.translate(word, src='en', dest='zh')
                            newly_translated_words.append((word, translation.text))
                        except:
                            st.warning(f"翻译 '{word}' 失败。")
                            newly_translated_words.append((word, ""))
                    status_bar.progress((i + 1) / len(words_to_translate))
                st.success("翻译处理完成！")

            final_words_dict = {word: translation for word, translation in ordered_words_data}
            for word_en, word_zh in newly_translated_words:
                final_words_dict[word_en] = word_zh

            words_data_for_audio = []
            for word, _ in ordered_words_data:
                words_data_for_audio.append((word, final_words_dict.get(word, "")))

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
                status_text.text(f"正在生成: {word} ({i+1}/{len(words_to_process)})")
                try:
                    word_audio = generate_word_audio(
                        word, translation, repeat_count, slow_speed, 
                        spell_pause_ms, word_pause_ms
                    )
                    combined_audio_segment += word_audio
                except Exception as e:
                    st.error(f"生成 '{word}' 音频失败: {e}")
                audio_progress.progress((i + 1) / len(words_to_process))

            if len(combined_audio_segment) > 0:
                timestamp = datetime.now().strftime("%y%m%d-%H%M%S")
                audio_buffer = BytesIO()
                combined_audio_segment.export(audio_buffer, format="mp3")
                audio_buffer.seek(0)
                st.success("🎉 音频生成成功！")
                st.audio(audio_buffer, format='audio/mp3')
                st.download_button("⬇️ 下载 MP3 音频", data=audio_buffer, file_name=f"dictation_{timestamp}.mp3", mime="audio/mp3")
            else:
                st.error("未能生成任何音频数据。")
    else:
        st.info("👈 请在上方选项卡中 [上传文件] 或 [输入单词列表] 以开始。")

if __name__ == "__main__":
    # 如果通过了密码检查，才运行主程序
    if check_password():
        run_main_app()
