"""Download model weights ahead of time (they are never committed to git).

    python -m speakloop.phoneme.download            # default lv-60 model
    python -m speakloop.phoneme.download --fast     # also the smaller xlsr-53 model
    python -m speakloop.phoneme.download --whisper  # Whisper-small for the benchmark baseline

Set HF_HOME to choose where the cache lives.
"""

from __future__ import annotations

import argparse

from .model import DEFAULT_MODEL, FAST_MODEL


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--whisper", action="store_true")
    a = ap.parse_args()
    from huggingface_hub import snapshot_download

    pats = ["*.json", "*.txt", "*.safetensors", "vocab*", "merges*"]
    names = [DEFAULT_MODEL] + ([FAST_MODEL] if a.fast else []) + (["openai/whisper-small"] if a.whisper else [])
    for n in names:
        print(n, "->", snapshot_download(n, allow_patterns=pats))


if __name__ == "__main__":
    main()
