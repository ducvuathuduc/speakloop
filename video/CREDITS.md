# Credits and licences — SpeakLoop launch film (v2)

| Asset | Source | Licence |
|---|---|---|
| Music score (`public/music.wav`, `public/music_teaser.wav`) | Synthesised from scratch by `scripts/make_music.py` (numpy/scipy oscillators and filtered noise; no samples, loops or third-party recordings). Mixed with the voice by `scripts/mix_audio.py` (voice at −16 LUFS, music at −18 LUFS ducked 9 dB under each line, −1 dBFS peak limit) into `public/mix_launch.wav` / `public/mix_teaser.wav` | Original work of the SpeakLoop author; released with this repo under the repo's licence. No third-party rights. |
| Voice lines (`public/vo/*.wav`): the learner's sentence “She walk to the shops yesterday.” and “Walked.” (voice `af_heart`), and four narration lines “A coach has to hear what you actually said.”, “Meet SpeakLoop.”, “Two point four times more real errors caught.”, “Speak a little every day.” (voice `af_bella`) | Generated offline on CPU by `scripts/make_voice.py` with **Kokoro-82M** (hexgrad/Kokoro-82M, v1.0) through `kokoro-onnx` 0.6.1, int8 ONNX export `kokoro-v1.0.int8.onnx` + `voices-v1.0.bin` (github.com/thewh1teagle/kokoro-onnx, release model-files-v1.0); phonemes via espeak-ng (`espeakng-loader`). Checked with faster-whisper small.en: every narration line transcribes as written. | Kokoro-82M weights: **Apache-2.0**. kokoro-onnx: MIT. espeak-ng: GPL-3.0, used only as a tool at generation time (not distributed with the film). Synthetic voices; no real person recorded or imitated. |
| Atkinson Hyperlegible Next (`public/atkinson-next-*.woff2`) | Braille Institute, via `speakloop-ui/ui/src/fonts` | SIL Open Font License 1.1 (`public/OFL-AtkinsonHyperlegibleNext.txt`) |
| SpeakLoop Phonetic (`public/speakloop-phonetic.woff2`) | Subset of Charis SIL 6.200, renamed (Reserved Font Name) | SIL Open Font License 1.1 (`public/OFL-CharisSIL.txt`) |
| SpeakLoop card UI (scenes “Reveal”, “The real card”, teaser card) | Rendered live in Remotion from the card's own components, vendored from `speakloop` feat/ui@383295b `ui/src` by `scripts/vendor_ui.py` (Preact → React transform, CSS scoped under `.slui`), fixture data marked “Demo data” on the card | Project's own work |
| SpeakLoop mark (`public/logo.svg`, and the in-card brand mark) | `assets/brand/logo-mark.svg` from feat/brand @9389ba6 (the /d/ loop mark) | Project's own work |

Benchmark figures on screen come verbatim from `benchmarks/RESULTS.md` (feat/phoneme): L2-ARCTIC, Vietnamese L1
speakers, held-out THV + TLV, same 100 utterances (3,200 annotated phones). SpeakLoop default P 0.589 / R 0.533 /
F1 0.560 vs Whisper-small transcript diff P 0.615 / R 0.219 / F1 0.323. mcp-lite-browser size: 8,627 B min+gzip
(mcp-lite-browser CHANGELOG).

"Alexa", "Amazon Bedrock" and "Whisper" are named only to describe the platform and the benchmark baseline.

Note on the hook: the learner line is synthesised from the phonemes /ʃiː wˈɔːk tə ðə ʃˈɑːps …/ (no /t/ on
“walk”), yet faster-whisper small.en and base.en both transcribe it as “She walked to the shops yesterday.”
That is the film's point in miniature: speech recognition hears the word you meant.
