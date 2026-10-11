"""Phoneme recogniser: lazy-loaded wav2vec2 CTC model emitting espeak IPA.

Weights are downloaded from the Hugging Face Hub on first use (or ahead of
time with ``python -m speakloop.phoneme.download``). Nothing is committed to git.

Environment variables
---------------------
SPEAKLOOP_PHONEME_MODEL   HF id or local path (default facebook/wav2vec2-lv-60-espeak-cv-ft)
SPEAKLOOP_PHONEME_DTYPE   float32 | bfloat16 (default float32)
SPEAKLOOP_PHONEME_THREADS torch intra-op threads (default: torch's choice)
"""

from __future__ import annotations

import io
import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

DEFAULT_MODEL = "facebook/wav2vec2-lv-60-espeak-cv-ft"
FAST_MODEL = "facebook/wav2vec2-xlsr-53-espeak-cv-ft"
SAMPLE_RATE = 16000
FRAME_SECONDS = 0.02  # wav2vec2 conv stride 320 samples @ 16 kHz

_lock = threading.Lock()
_cache: dict[tuple[str, str], "PhonemeModel"] = {}


def load_audio(audio: bytes | bytearray | str | os.PathLike | np.ndarray,
               sample_rate: int | None = None) -> np.ndarray:
    """Return mono float32 audio at 16 kHz from WAV/FLAC bytes, a path, or an array."""
    import soundfile as sf

    if isinstance(audio, np.ndarray):
        wav, sr = audio.astype(np.float32), sample_rate or SAMPLE_RATE
    else:
        src = io.BytesIO(bytes(audio)) if isinstance(audio, (bytes, bytearray)) else str(audio)
        wav, sr = sf.read(src, dtype="float32", always_2d=False)
    if wav.ndim == 2:
        wav = wav.mean(axis=1)
    if sr != SAMPLE_RATE:
        from scipy.signal import resample_poly
        from math import gcd

        g = gcd(int(sr), SAMPLE_RATE)
        wav = resample_poly(wav, SAMPLE_RATE // g, int(sr) // g).astype(np.float32)
    return np.ascontiguousarray(wav, dtype=np.float32)


@dataclass
class Emissions:
    log_probs: np.ndarray  # (T, V) float32 log-softmax
    frame_seconds: float = FRAME_SECONDS


class PhonemeModel:
    def __init__(self, name: str = DEFAULT_MODEL, dtype: str = "float32"):
        import torch
        from transformers import AutoFeatureExtractor, Wav2Vec2ForCTC

        threads = os.environ.get("SPEAKLOOP_PHONEME_THREADS")
        if threads:
            torch.set_num_threads(int(threads))
        self.name = name
        self.dtype = getattr(torch, dtype)
        self.extractor = AutoFeatureExtractor.from_pretrained(name)
        self.model = Wav2Vec2ForCTC.from_pretrained(name, dtype=self.dtype).eval()
        self.vocab: dict[str, int] = _load_vocab(name)
        self.id2tok = {i: t for t, i in self.vocab.items()}
        self.blank_id = self.vocab.get("<pad>", 0)

    def emissions(self, wav: np.ndarray) -> Emissions:
        import torch

        x = self.extractor(wav, sampling_rate=SAMPLE_RATE, return_tensors="pt").input_values
        with torch.inference_mode():
            logits = self.model(x.to(self.dtype)).logits[0].float()
            lp = torch.log_softmax(logits, dim=-1).numpy()
        return Emissions(lp)

    def greedy_tokens(self, em: Emissions) -> list[str]:
        ids = em.log_probs.argmax(-1)
        out, prev = [], None
        for i in ids:
            if i != prev and i != self.blank_id:
                tok = self.id2tok.get(int(i), "")
                if tok and not tok.startswith("<"):
                    out.append(tok)
            prev = i
        return out


def _load_vocab(name: str) -> dict[str, int]:
    p = Path(name)
    if p.is_dir() and (p / "vocab.json").exists():
        return json.loads((p / "vocab.json").read_text())
    from huggingface_hub import hf_hub_download

    return json.loads(Path(hf_hub_download(name, "vocab.json")).read_text())


def get_model(name: str | None = None, dtype: str | None = None) -> PhonemeModel:
    name = name or os.environ.get("SPEAKLOOP_PHONEME_MODEL", DEFAULT_MODEL)
    dtype = dtype or os.environ.get("SPEAKLOOP_PHONEME_DTYPE", "float32")
    key = (name, dtype)
    with _lock:
        if key not in _cache:
            _cache[key] = PhonemeModel(name, dtype)
        return _cache[key]
