# Latency and memory — `speakloop.phoneme.assess()`

Smoke benchmark, **not** an accuracy evaluation: 3 L2-ARCTIC Vietnamese
utterances (HQTV a0003 / a0005 / a0006) plus the espeak fixture
`tests/fixtures/espeak_she_walked.wav`, 3 calls each, one model loaded once.

    SPEAKLOOP_PHONEME_MODEL=./models/lv60-bf16   # python -m speakloop.phoneme.convert facebook/wav2vec2-lv-60-espeak-cv-ft ./models/lv60-bf16
    SPEAKLOOP_PHONEME_DTYPE=float32 SPEAKLOOP_PHONEME_THREADS=2 \
    SPEAKLOOP_BENCH_DATA=/path/to/l2arctic python -m benchmarks.latency --repeats 3

## Machine

2 vCPU ARM Neoverse-V2 (has bf16), ~3.5–4.5 GB free RAM, shared with other
jobs (load average 2–12 during runs); model files on a network filesystem
(JuiceFS), so **load times are I/O-bound and pessimistic**. torch 2.14.1+cpu,
transformers 5.19.0, espeak-ng 1.52.

## Results — `facebook/wav2vec2-lv-60-espeak-cv-ft`, fp32 compute (2026-10-11)

Weights stored as bf16 safetensors (0.63 GB), loaded with `dtype=float32`.

| clip | audio s | call 1 ms | call 2 ms | call 3 ms |
|---|---|---|---|---|
| HQTV_arctic_a0003 | 5.30 | 7465 (cold) | 1994 | 1826 |
| HQTV_arctic_a0005 | 1.72 | 720 | 699 | 969 |
| HQTV_arctic_a0006 | 4.09 | 2501 | 1722 | 1434 |
| espeak fixture | 1.90 | 767 | 687 | 715 |

* **Warm end-to-end latency (calls 2–3, n=8): p50 1202 ms, p95 1935 ms.**
* Real-time factor ≈ 0.35–0.40 (acoustic model is >90% of the time; G2P <10 ms
  warm, GOP scoring 5–55 ms).
* First call after load: 7.5 s (lazy init, page faults).
* Model load: 169 s on this filesystem (would be seconds on local SSD).
* **Peak RSS: 2335 MB** (reached during load, bf16 → fp32 upcast).

## bf16 compute — not usable on this CPU

Same weights with `SPEAKLOOP_PHONEME_DTYPE=bfloat16`: RSS stayed ~1.0 GB but
the first a0003 call took **101 s** (acoustic 88 s) vs 7.5 s in fp32, and a
warm call ~100 s under contention. Run aborted after one clip. torch's CPU
bf16 path for this model is far slower than fp32 here, so: store bf16, compute
fp32.

Loading the upstream hub checkpoint (`pytorch_model.bin`, fp32 1.26 GB) with
`dtype=bfloat16` directly was killed at ~60% of weight loading on this shared
box (likely OOM, no traceback); `speakloop.phoneme.convert` avoids that by
converting from a memory-mapped source.

## Not measured

* `facebook/wav2vec2-xlsr-53-espeak-cv-ft` (same 300M-param size, so expect similar numbers).
* Accuracy/F1 against L2-ARCTIC annotations — see the full benchmark, not this file.

Raw numbers: `bench_cache/latency_lv60_fp32.json` (git-ignored).
