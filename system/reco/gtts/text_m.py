from gtts import gTTS
import os
import re
from pydub import AudioSegment
from pydub.playback import play

# 提取中英文分段
def split_text_by_language(text):
    pattern = r'([\u4e00-\u9fff，。！？、“”]+|[a-zA-Z0-9\s,.\'":;!?]+)'
    segments = re.findall(pattern, text)
    return [seg.strip() for seg in segments if seg.strip()]

# 判断段落语言
def detect_lang(segment):
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', segment)
    return 'zh-cn' if len(chinese_chars) > len(segment) / 2 else 'en'

# 合成音频并保存临时文件
def synthesize_segment(segment, lang, index):
    tts = gTTS(text=segment, lang=lang, slow=False)
    filename = f"segment_{index}.mp3"
    tts.save(filename)
    return filename

# 主函数：处理文件，分段生成，合并
def generate_tts_from_mixed_text(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read().strip()

    segments = split_text_by_language(text)
    print("分段结果：", segments)

    audio_files = []
    for i, seg in enumerate(segments):
        lang = detect_lang(seg)
        file = synthesize_segment(seg, lang, i)
        audio_files.append(file)

    # 合并音频
    combined = AudioSegment.empty()
    for file in audio_files:
        combined += AudioSegment.from_file(file)
        os.remove(file)  # 删除临时段落文件

    output_path = "output.mp3"
    combined.export(output_path, format="mp3")
    print(f"已保存合成语音到 {output_path}")
    # os.system(f"start {output_path}")  # 播放（Windows）

# 输入 txt 文件路径
generate_tts_from_mixed_text("output.txt")
