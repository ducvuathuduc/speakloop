"""Shrink a wav2vec2 espeak checkpoint to a local bf16 safetensors folder.

    python -m speakloop.phoneme.convert facebook/wav2vec2-lv-60-espeak-cv-ft ./models/lv60-bf16
    SPEAKLOOP_PHONEME_MODEL=./models/lv60-bf16 SPEAKLOOP_PHONEME_DTYPE=float32 ...

Halves the on-disk size (1.26 GB -> 0.63 GB) and converts tensor by tensor
from a memory-mapped source, so it runs on small machines where loading the
upstream pytorch_model.bin with ``dtype=bfloat16`` gets OOM-killed.

Note: on CPU, *computing* in bf16 was 20-50x slower than fp32 in our test
(benchmarks/LATENCY.md). Store bf16, load with SPEAKLOOP_PHONEME_DTYPE=float32.
"""

from __future__ import annotations

import glob
import os
import shutil
import sys

AUX = ("config.json", "preprocessor_config.json", "vocab.json",
       "tokenizer_config.json", "special_tokens_map.json")


def convert(src: str, dst: str) -> int:
    import torch
    from safetensors import safe_open
    from safetensors.torch import save_file

    if os.path.isdir(src):
        snaps = [src]
    else:
        from huggingface_hub import snapshot_download

        snaps = [snapshot_download(src, allow_patterns=["*.json", "*.safetensors", "*.bin"])]
    os.makedirs(dst, exist_ok=True)
    for s in snaps:
        for f in AUX:
            if os.path.exists(os.path.join(s, f)):
                shutil.copy(os.path.join(s, f), os.path.join(dst, f))

    def cast(t):
        return t.to(torch.bfloat16) if t.is_floating_point() else t.clone()

    out = {}
    st = [p for s in snaps for p in glob.glob(os.path.join(s, "model.safetensors"))]
    if st:
        with safe_open(st[0], "pt") as fh:
            for k in fh.keys():
                out[k] = cast(fh.get_tensor(k))
    else:
        binp = [p for s in snaps for p in glob.glob(os.path.join(s, "pytorch_model.bin"))][0]
        sd = torch.load(binp, mmap=True, weights_only=True, map_location="cpu")
        for k, t in sd.items():
            out[k] = cast(t)
    save_file({k: v.contiguous() for k, v in out.items()}, os.path.join(dst, "model.safetensors"),
              metadata={"format": "pt"})
    return len(out)


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    n = convert(sys.argv[1], sys.argv[2])
    print(f"wrote {n} tensors to {sys.argv[2]}")


if __name__ == "__main__":
    main()
