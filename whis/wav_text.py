import sounddevice as sd
import numpy as np
import queue
import whisper
from opencc import OpenCC
from scipy.io.wavfile import write
from typing import List
from datetime import datetime
import threading
import os

class VoiceRecognizer:
    def __init__(self,on_transcription=None):
        self.model = whisper.load_model("./whis/tiny.pt")
        self.cc = OpenCC("t2s")
        self.output_dir = "./whis/test"
        os.makedirs(self.output_dir, exist_ok=True)
        self.SAMPLE_RATE = 16000
        self.CHANNELS = 1
        self.CHUNK_SIZE = 1024
        self.SILENCE_THRESHOLD = 150
        self.SILENCE_DURATION = 1.5
        self.MAX_RECORD_SECONDS = 30
        self.SILENCE_CHUNK_LIMIT = int(self.SILENCE_DURATION * self.SAMPLE_RATE / self.CHUNK_SIZE)

        self.audio_queue = queue.Queue()
        self.latest_transcription = ""
        self.on_transcription = on_transcription
        self.stop_event = threading.Event()

    def is_silent(self, chunk: np.ndarray) -> bool:
        volume = np.linalg.norm(chunk) / np.sqrt(chunk.size)
        return volume < self.SILENCE_THRESHOLD

    def record_until_silence(self) -> np.ndarray:
        recorded_chunks: List[np.ndarray] = []
        silent_chunks = 0
        total_chunks = 0
        max_chunks = int(self.SAMPLE_RATE * self.MAX_RECORD_SECONDS / self.CHUNK_SIZE)

        while total_chunks < max_chunks:
            chunk = self.audio_queue.get()
            recorded_chunks.append(chunk)
            total_chunks += 1

            if self.is_silent(chunk):
                silent_chunks += 1
            else:
                silent_chunks = 0

            if silent_chunks >= self.SILENCE_CHUNK_LIMIT:
                print("检测到静音，录音结束。")
                break

        return np.concatenate(recorded_chunks, axis=0)

    def audio_callback(self, indata, frames, time_info, status):
        if status:
            print(f"音频流状态警告: {status}")
        self.audio_queue.put(indata.copy())

    def listen_and_transcribe(self):
        print("正在持续监听（保持静音以等待触发）...")

        with sd.InputStream(samplerate=self.SAMPLE_RATE, channels=self.CHANNELS, dtype='int16',
                            blocksize=self.CHUNK_SIZE, callback=self.audio_callback):
            while not self.stop_event.is_set():
                chunk = self.audio_queue.get()
                if not self.is_silent(chunk):
                    print("检测到讲话，开始录音...")
                    audio_data = np.concatenate([chunk, self.record_until_silence()], axis=0)

                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    audio_path = os.path.join(self.output_dir, f"record_{timestamp}.wav")
                    write(audio_path, self.SAMPLE_RATE, audio_data)
                    print(f"音频保存: {audio_path}")

                    print("正在转录语音...")
                    result = self.model.transcribe(audio_path, language="zh")
                    text = self.cc.convert(result["text"])
                    self.latest_transcription = text

                    if self.on_transcription:#调用外部注册的回调函数
                        print("触发转写回调...")
                        self.on_transcription(text)  

                    print(f"语音内容: {text}")

                    txt_path = os.path.join(self.output_dir, f"转写_{timestamp}.txt")
                    with open(txt_path, "a", encoding="utf-8") as f:
                        f.write(f"[语音] {text}\n")

                    print("转录完成，继续监听...\n")

    def start(self):
        """启动监听线程"""
        self.listen_and_transcribe()

    def stop(self):
        """停止监听"""
        print("语音识别已请求停止...")
        self.stop_event.set()
