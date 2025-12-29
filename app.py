import streamlit as st
import gtts
import pydu
from gtts import gTTS
from pydub import AudioSegment
import os
import time
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

@st.cache_resource
def get_gtts_translator():
    return Translator()

def create_audio_segment(text, lang='en', slow=False):
    """使用gTTS生成文本的音频片段"""
    tts = gTTS(text=text, lang=lang, slow=slow)
    fp = BytesIO()
    tts.write_to_fp(fp)
    fp.seek(0)
    return AudioSegment.from_file(fp, format="mp3")

def generate_word_audio(word, translation, repeat_count, slow_speed, spell_pause_ms, word_pause_ms):
    """生成单个单词的完整听写音频片段，包含英文单词、拼读和中文翻译"""
    full_word_audio_normal = create_audio_segment(word, slow=False)
    full_word_audio_slow = create_audio_segment(word, slow=True)

    spelling_audio_segments = []
    for char in word.replace(' ', ''): # 忽略空格进行拼读
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

def main_app():
    st.set_page_config(layout="wide")
    st.title("📝 听写音频生成器")

    st.markdown("""
    这个应用可以帮助你根据单词列表生成听写音频。它会自动翻译缺失的中文意思，并支持自定义朗读参数。
    --- 
    **使用步骤**:
    1.  上传一个 `word.txt` 文件。
    2.  调整左侧边栏的参数。
    3.  点击 `生成音频` 按钮。
    4.  下载生成的MP3文件。
    """)

    uploaded_file = st.file_uploader("上传单词列表文件 (word.txt)", type=["txt"])
    
    st.sidebar.header("⚙️ 配置项")
    repeat_count = st.sidebar.number_input("每个单词朗读次数", min_value=1, max_value=5, value=DEFAULT_REPEAT_COUNT)
    words_per_file = st.sidebar.number_input("处理单词总数 (0表示所有单词)", min_value=0, value=DEFAULT_WORDS_PER_FILE)
    slow_speed = st.sidebar.checkbox("慢速朗读", value=DEFAULT_SLOW_SPEED)
    spell_pause_ms = st.sidebar.slider("拼读字母间停顿 (毫秒)", min_value=0, max_value=500, value=DEFAULT_SPELL_PAUSE_MS)
    word_pause_ms = st.sidebar.slider("单词朗读与拼读间停顿 (毫秒)", min_value=0, max_value=1000, value=DEFAULT_WORD_PAUSE_MS)

    if uploaded_file is not None:
        # Save uploaded file to a temporary location for processing
        temp_word_file_path = os.path.join("/tmp", uploaded_file.name)
        with open(temp_word_file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        st.success(f"文件 '{uploaded_file.name}' 已成功上传。")

        if st.button("生成音频"): # Moved button here
            st.info("正在处理单词和生成音频...请稍候。")
            words_to_translate = []
            ordered_words_data = []
            
            try:
                with open(temp_word_file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        stripped_line = line.strip()
                        if not stripped_line:
                            continue
                        parts = stripped_line.split(',', 1)
                        english_word = parts[0].strip()
                        chinese_translation = parts[1].strip() if len(parts) > 1 else ''

                        if not chinese_translation:
                            words_to_translate.append(english_word)
                        ordered_words_data.append((english_word, chinese_translation))

            except FileNotFoundError:
                st.error(f"错误：找不到单词文件 '{uploaded_file.name}'。")
                return

            newly_translated_words = []
            if words_to_translate:
                translator = get_gtts_translator()
                st.write(f"正在翻译 {len(words_to_translate)} 个单词...")
                for word in words_to_translate:
                    try:
                        translation = translator.translate(word, src='en', dest='zh')
                        newly_translated_words.append((word, translation.text))
                        st.write(f"已翻译 '{word}' 为 '{translation.text}'")
                    except Exception as e:
                        st.warning(f"翻译 '{word}' 时发生错误: {e}")
                        newly_translated_words.append((word, "Translation Error"))
                st.success("翻译完成！")

            final_words_dict = {word: translation for word, translation in ordered_words_data}
            for word_en, word_zh in newly_translated_words:
                final_words_dict[word_en] = word_zh

            file_content = []
            for word, original_translation in ordered_words_data:
                translation = final_words_dict.get(word, original_translation)
                file_content.append(f"{word},{translation}")

            try:
                # Overwrite the temp file with updated translations
                with open(temp_word_file_path, 'w', encoding='utf-8') as f:
                    for line in file_content:
                        f.write(line + '\n')
                st.success(f"单词文件 '{uploaded_file.name}' 已更新。")
            except Exception as e:
                st.error(f"更新单词文件 '{uploaded_file.name}' 时发生错误: {e}")
                return

            # --- Audio Generation Logic ---
            words_data_for_audio = []
            try:
                with open(temp_word_file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        stripped_line = line.strip()
                        if not stripped_line:
                            continue
                        parts = stripped_line.split(',', 1)
                        english_word = parts[0].strip()
                        chinese_translation = parts[1].strip() if len(parts) > 1 else None
                        words_data_for_audio.append((english_word, chinese_translation))
            except FileNotFoundError:
                st.error("音频生成：找不到更新后的单词文件。")
                return

            if not words_data_for_audio:
                st.warning("单词文件为空，没有单词可以生成音频。")
                return

            words_to_process_limit = words_per_file if words_per_file > 0 else len(words_data_for_audio)
            words_to_process = words_data_for_audio[:words_to_process_limit]
            st.write(f"将从 '{uploaded_file.name}' 读取前 {len(words_to_process)} 个单词（及其翻译）生成音频...")

            combined_audio_segment = AudioSegment.empty()
            progress_bar = st.progress(0)
            status_text = st.empty()

            for i, (word, translation) in enumerate(words_to_process):
                translation_info = f" ({translation})" if translation else ""
                status_text.text(f"正在生成单词音频：{word}{translation_info} ({i+1}/{len(words_to_process)})...")
                try:
                    word_audio = generate_word_audio(word,
                                                     translation,
                                                     repeat_count,
                                                     slow_speed,
                                                     spell_pause_ms,
                                                     word_pause_ms)
                    combined_audio_segment += word_audio
                    progress_bar.progress((i + 1) / len(words_to_process))

                except Exception as e:
                    st.error(f"生成单词 '{word}' 音频时发生错误: {e}")
                    continue

            if combined_audio_segment:
                timestamp = datetime.now().strftime("%y%m%d-%H%M%S")
                output_filename = os.path.join(OUTPUT_DIR, f"dictation_combined_{timestamp}.mp3")
                
                # Export audio to a BytesIO object for download
                audio_buffer = BytesIO()
                combined_audio_segment.export(audio_buffer, format="mp3")
                audio_buffer.seek(0)

                st.success("所有单词音频生成完毕！")
                st.audio(audio_buffer.getvalue(), format='audio/mp3') # Play preview

                st.download_button(
                    label="下载生成的音频文件",
                    data=audio_buffer.getvalue(),
                    file_name=f"dictation_combined_{timestamp}.mp3",
                    mime="audio/mp3"
                )
            else:
                st.warning("没有生成任何音频内容。")
            status_text.empty() # Clear status text after completion

    st.markdown("""
    --- 
    **关于 `gTTS` 语言代码的提示**: `gTTS` 对 `zh-cn` 等语言代码可能显示弃用警告，这是库内部的提示，不影响功能。我们已在代码中使用 `zh` 以提高兼容性。
    """)


if __name__ == "__main__":

    main_app()
