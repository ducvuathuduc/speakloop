"""Generate the film's voice lines offline on CPU with Kokoro-82M (Apache-2.0) via kokoro-onnx (MIT).

pip install kokoro-onnx soundfile
curl -LO https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx
curl -LO https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
python3 scripts/make_voice.py <dir with the two model files>      -> public/vo/*.wav (24 kHz mono)
"""
import sys
from pathlib import Path

import soundfile as sf
from kokoro_onnx import Kokoro

LINES = {  # clip: (voice, text)
    "learner": ("af_heart", "She walk to the shops yesterday."),  # phonemes /wˈɔːk/: no /t/
    "walked": ("af_heart", "Walked."),
    "coach": ("af_bella", "A coach has to hear what you actually said."),
    "meet": ("af_bella", "Meet SpeakLoop."),
    "proof": ("af_bella", "Two point four times more real errors caught."),
    "close": ("af_bella", "Speak a little every day."),
}
models = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
out = Path(__file__).resolve().parent.parent / "public" / "vo"
out.mkdir(parents=True, exist_ok=True)
k = Kokoro(str(models / "kokoro-v1.0.int8.onnx"), str(models / "voices-v1.0.bin"))
for clip, (voice, text) in LINES.items():
    audio, sr = k.create(text, voice=voice, speed=1.0, lang="en-us")
    sf.write(out / f"{clip}.wav", audio, sr)
    print(clip, voice, f"{len(audio) / sr:.2f}s", k.tokenizer.phonemize(text, "en-us"))
