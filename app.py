import streamlit as st
import asyncio
import edge_tts
from pydub import AudioSegment
import os
from datetime import datetime
from deep_translator import GoogleTranslator
from io import BytesIO

# --- Configuration Defaults ---
DEFAULT_REPEAT_COUNT = 2
DEFAULT_WORDS_PER_FILE = 10
DEFAULT_SLOW_SPEED = False
DEFAULT_SPELL_PAUSE_MS = 50  # 拼读停顿稍微给一点点，不然太赶
DEFAULT_WORD_PAUSE_MS = 300
OUTPUT_DIR = "audio_output"

# --- Initialization ---
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

# --- Helper Functions ---

async def _edge_tts_generate(text, voice, rate):
    """底层异步生成函数"""
    # 这里的 rate 参数可以控制语速，例如 "+50%"
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    fp = BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            fp.write(chunk["data"])
    fp.seek(0)
    return fp

def create_audio_segment(text, lang='en', slow=False, is_spelling=False):
    """
    使用 Edge-TTS 生成音频。
    增加 is_spelling 参数：如果是拼读字母，强制加速
    """
    # 1. 选择语音角色
    if lang == 'zh':
        voice = "zh-CN-XiaoxiaoNeural" # 中文女声
    else:
        voice = "en-US-JennyNeural"    # 英文女声
    
    # 2. 设置语速
    # 正常朗读: +0%
    # 慢速模式: -20%
    # 拼读模式: +40% (让字母读得更快！)
    if is_spelling:
        rate = "+40%" 
    elif slow:
        rate = "-20%"
    else:
        rate = "+0%"
    
    try:
        fp = asyncio.run(_edge_tts_generate(text, voice, rate))
        return AudioSegment.from_file(fp, format="mp3")
    except Exception as e:
        print(f"Error creating audio for {text}: {e}")
        return AudioSegment.silent(duration=500)

def get_translation(text):
    """使用 deep_translator 的 Google 接口 (Streamlit Cloud上最稳)"""
    try:
        # 自动检测源语言，翻译成简体中文
        translator = GoogleTranslator(source='auto', target='zh-CN')
        return translator.translate(text)
    except Exception as e:
        print(f"Translation error: {e}")
        return None

def generate_word_audio(word, translation, repeat_count, slow_speed, spell_pause_ms, word_pause_ms):
    """生成单个单词的完整听写音频片段"""
    
    # 1. 生成单词音频 (正常 & 慢速)
    full_word_audio_normal = create_audio_segment(word, lang='en', slow=False)
    full_word_audio_slow = create_audio_segment(word, lang='en', slow=True)

    # 2. 生成拼读音频 (S-P-E-L-L) -> ⚡️这里开启了加速模式
    spelling_audio_segments = []
    # 只提取字母，避免读出符号
    clean_word = ''.join(filter(str.isalpha, word))
    
    for char in clean_word:
        # is_spelling=True 会让字母读得更快
        char_audio = create_audio_segment(char, lang='en', is_spelling=True)
        spelling_audio_segments.append(char_audio)
        # 加上微小的停顿
        spelling_audio_segments.append(AudioSegment.silent(duration=spell_pause_ms))

    spelling_combined = AudioSegment.empty()
    if spelling_audio_segments:
        spelling_combined = sum(spelling_audio_segments[:-1])

    # 3. 组合音频
    word_final_audio = AudioSegment.empty()

    # A. 单词 (重复 N 次)
    for _ in range(repeat_count):
        word_final_audio += full_word_audio_normal if not slow_speed else full_word_audio_slow
    
    # B. 停顿 -> 拼读 -> 停顿
    word_final_audio += AudioSegment.silent(duration=word_pause_ms)
    word_final_audio += spelling_combined
    word_final_audio += AudioSegment.silent(duration=word_pause_ms)
    
    # C. 单词 (再读一次)
    word_final_audio += full_word_audio_normal if not slow_speed else full_word_audio_slow
    word_final_audio += AudioSegment.silent(duration=word_pause_ms)

    # D. 中文翻译
    if translation:
        chinese_audio = create_audio_segment(translation, lang='zh', slow=False)
        word_final_audio += chinese_audio

    # E. 单词间大停顿
    word_final_audio += AudioSegment.silent(duration=word_pause_ms * 2)

    return word_final_audio

# --- Authentication ---
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
    st.title("📝 听写音频生成器 (Pro版)")
    st.markdown("集成 **Edge 神经网络语音** (更自然) 与 **Google 翻译** (更精准)。")

    st.sidebar.header("⚙️ 配置项")
    repeat_count = st.sidebar.number_input("每个单词朗读次数", min_value=1, max_value=5, value=DEFAULT_REPEAT_COUNT)
    words_per_file = st.sidebar.number_input("处理单词总数 (0表示所有单词)", min_value=0, value=DEFAULT_WORDS_PER_FILE)
    
    # 现在慢速朗读功能已经生效了 (-20%)
    slow_speed = st.sidebar.checkbox("慢速朗读单词", value=DEFAULT_SLOW_SPEED)
    
    # 这里的停顿是字母音频之间的空白，建议设小一点，比如 50ms-100ms
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
            st.info(f"正在处理: {source_name}...")
            
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
                st.write(f"正在翻译 {len(words_to_translate)} 个单词...")
                for i, word in enumerate(words_to_translate):
                    trans_text = get_translation(word)
                    if trans_text:
                        newly_translated_words.append((word, trans_text))
                    else:
                        st.warning(f"翻译 '{word}' 失败，请检查网络或单词拼写。")
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
                st.success("🎉 生成成功！")
                st.audio(audio_buffer, format='audio/mp3')
                st.download_button("⬇️ 下载 MP3", data=audio_buffer, file_name=f"dictation_{timestamp}.mp3", mime="audio/mp3")
            else:
                st.error("生成失败。")
    else:
        st.info("👈 请上传或输入。")

if __name__ == "__main__":
    if check_password():
        run_main_app()
