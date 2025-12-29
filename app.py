import streamlit as st
import asyncio
import edge_tts
from pydub import AudioSegment
import os
from datetime import datetime
from deep_translator import MicrosoftTranslator
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

# Edge-TTS 是异步的，需要在这个函数里运行
async def _edge_tts_generate(text, voice):
    """底层异步生成函数"""
    communicate = edge_tts.Communicate(text, voice)
    # 将音频写入内存 BytesIO
    fp = BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            fp.write(chunk["data"])
    fp.seek(0)
    return fp

def create_audio_segment(text, lang='en', slow=False):
    """
    使用 Edge-TTS 生成音频。
    lang='en' -> 使用美式英语 (en-US-JennyNeural)
    lang='zh' -> 使用中文 (zh-CN-XiaoxiaoNeural)
    slow -> Edge-TTS 支持调整速率，这里简单模拟
    """
    # 映射语言到具体的微软语音角色
    # 你可以选: en-US-GuyNeural (男), en-US-JennyNeural (女)
    # zh-CN-YunxiNeural (男), zh-CN-XiaoxiaoNeural (女)
    if lang == 'zh':
        voice = "zh-CN-XiaoxiaoNeural"
    else:
        voice = "en-US-JennyNeural"
    
    # 调整语速
    rate = "-20%" if slow else "+0%"
    
    # 因为 Edge-TTS 是异步库，Streamlit 是同步的，我们需要用 asyncio.run
    try:
        # 注意：communicate 对象本身不支持直接加 rate 参数，
        # 简单起见，这里暂不通过 API 调整 rate，而是依赖 pydub 后期处理或忽略
        # 如果非常需要慢速，edge-tts 可以在文本中通过 SSML 标签控制，或者简单点不处理
        
        # 运行异步任务
        fp = asyncio.run(_edge_tts_generate(text, voice))
        return AudioSegment.from_file(fp, format="mp3")
    except Exception as e:
        print(f"Error creating audio for {text}: {e}")
        return AudioSegment.silent(duration=500)

def get_translation(text):
    """使用 deep_translator 调用微软翻译 (无需Key)"""
    try:
        # target='zh-Hans' 是微软的简体中文代码
        translator = MicrosoftTranslator(source='en', target='zh-Hans')
        return translator.translate(text)
    except Exception as e:
        print(f"Translation error: {e}")
        return None

def generate_word_audio(word, translation, repeat_count, slow_speed, spell_pause_ms, word_pause_ms):
    """生成单个单词的完整听写音频片段"""
    
    # 1. 生成单词音频 (Edge-TTS 质量很高，慢速可以忽略，或者你可以做特殊处理)
    full_word_audio_normal = create_audio_segment(word, lang='en', slow=False)
    # Edge-TTS 如果不做 SSML 处理，慢速和常速是一样的，这里为了逻辑兼容先复用
    full_word_audio_slow = create_audio_segment(word, lang='en', slow=True) 

    # 2. 生成拼读音频 (S-P-E-L-L)
    spelling_audio_segments = []
    clean_word = ''.join(filter(str.isalpha, word))
    
    for char in clean_word:
        # 字母朗读
        char_audio = create_audio_segment(char, lang='en', slow=False)
        spelling_audio_segments.append(char_audio)
        spelling_audio_segments.append(AudioSegment.silent(duration=spell_pause_ms))

    spelling_combined = AudioSegment.empty()
    if spelling_audio_segments:
        spelling_combined = sum(spelling_audio_segments[:-1])

    # 3. 组合
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

# --- Authentication (保留你的密码功能) ---
def check_password():
    if "PASSWORD" in st.secrets:
        secret_password = st.secrets["PASSWORD"]
    else:
        secret_password = "123456"

    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False

    if st.session_state.password_correct:
        return True

    st.set_page_config(page_title="登录 - 听写生成器")
    st.title("🔒 请输入访问密码")
    password_input = st.text_input("密码", type="password")
    if st.button("登录"):
        if password_input == secret_password:
            st.session_state.password_correct = True
            st.rerun()
        else:
            st.error("❌ 密码错误")
    return False

# --- Main App ---

def run_main_app():
    st.title("📝 听写音频生成器 (国内优化版)")
    st.markdown("使用 **Microsoft Edge 语音引擎** 和 **微软翻译**，国内访问更稳定，语音更自然。")

    st.sidebar.header("⚙️ 配置项")
    repeat_count = st.sidebar.number_input("每个单词朗读次数", min_value=1, max_value=5, value=DEFAULT_REPEAT_COUNT)
    words_per_file = st.sidebar.number_input("处理单词总数 (0表示所有单词)", min_value=0, value=DEFAULT_WORDS_PER_FILE)
    slow_speed = st.sidebar.checkbox("慢速朗读 (目前Edge版本暂不支持变速)", value=False, disabled=True)
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
        user_text = st.text_area("在此输入或粘贴单词列表", height=200, placeholder="Apple\nBanana,香蕉")
        if user_text.strip():
            if not uploaded_file: 
                with open(temp_word_file_path, "w", encoding="utf-8") as f:
                    f.write(user_text)
                has_valid_input = True
                source_name = "手动输入列表"
                st.success("已加载手动输入的文本")
            elif uploaded_file:
                st.info("⚠️ 优先使用上传的文件。")

    if has_valid_input:
        st.divider()
        if st.button("🎵 开始生成音频", type="primary"):
            st.info(f"正在使用 Edge AI 处理: {source_name}...")
            
            words_to_translate = []
            ordered_words_data = []
            
            try:
                with open(temp_word_file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        stripped_line = line.strip()
                        if not stripped_line: continue
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
                status_bar = st.progress(0)
                st.write(f"正在调用微软翻译 {len(words_to_translate)} 个单词...")
                for i, word in enumerate(words_to_translate):
                    trans_text = get_translation(word)
                    if trans_text:
                        newly_translated_words.append((word, trans_text))
                    else:
                        st.warning(f"翻译 '{word}' 失败。")
                        newly_translated_words.append((word, ""))
                    status_bar.progress((i + 1) / len(words_to_translate))
                st.success("翻译完成！")

            final_words_dict = {word: translation for word, translation in ordered_words_data}
            for word_en, word_zh in newly_translated_words:
                final_words_dict[word_en] = word_zh

            words_data_for_audio = []
            for word, _ in ordered_words_data:
                words_data_for_audio.append((word, final_words_dict.get(word, "")))

            if not words_data_for_audio:
                st.warning("无数据。")
                return

            limit = words_per_file if words_per_file > 0 else len(words_data_for_audio)
            words_to_process = words_data_for_audio[:limit]
            
            st.write(f"正在生成高清语音 ({len(words_to_process)}个)...")
            
            combined_audio_segment = AudioSegment.empty()
            audio_progress = st.progress(0)
            status_text = st.empty()

            for i, (word, translation) in enumerate(words_to_process):
                status_text.text(f"Generating: {word} ({i+1}/{len(words_to_process)})")
                try:
                    word_audio = generate_word_audio(
                        word, translation, repeat_count, slow_speed, 
                        spell_pause_ms, word_pause_ms
                    )
                    combined_audio_segment += word_audio
                except Exception as e:
                    st.error(f"Error: {e}")
                audio_progress.progress((i + 1) / len(words_to_process))

            if len(combined_audio_segment) > 0:
                timestamp = datetime.now().strftime("%y%m%d-%H%M%S")
                audio_buffer = BytesIO()
                combined_audio_segment.export(audio_buffer, format="mp3")
                audio_buffer.seek(0)
                st.success("🎉 生成成功！试听一下 Edge AI 的效果吧：")
                st.audio(audio_buffer, format='audio/mp3')
                st.download_button("⬇️ 下载 MP3", data=audio_buffer, file_name=f"dictation_{timestamp}.mp3", mime="audio/mp3")
            else:
                st.error("生成失败。")
    else:
        st.info("👈 请上传或输入。")

if __name__ == "__main__":
    if check_password():
        run_main_app()
