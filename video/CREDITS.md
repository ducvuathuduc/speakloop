# Credits and licences — SpeakLoop launch film

| Asset | Source | Licence |
|---|---|---|
| Music score (`public/music.wav`, `public/music_teaser.wav`) | Synthesised from scratch by `scripts/make_music.py` (numpy/scipy oscillators and filtered noise; no samples, loops or third-party recordings) | Original work of the SpeakLoop author; released with this repo under the repo's licence. No third-party rights. |
| Learner voice line "She walk to the shops yesterday." (`public/learner.mp3`) | Generated with Microsoft Edge neural TTS (`edge-tts`, voice `vi-VN-HoaiMyNeural`) — a Vietnamese voice reading English, standing in for a learner | Synthetic voice, same method as the previous demo video; no real person recorded. |
| Atkinson Hyperlegible Next (`public/atkinson-next-*.woff2`) | Braille Institute, via `speakloop-ui/ui/src/fonts` | SIL Open Font License 1.1 (`public/OFL-AtkinsonHyperlegibleNext.txt`) |
| SpeakLoop Phonetic (`public/speakloop-phonetic.woff2`) | Subset of Charis SIL 6.200, renamed (Reserved Font Name) | SIL Open Font License 1.1 (`public/OFL-CharisSIL.txt`) |
| Card screenshots (`public/*-dark-1280x800.png`) | SpeakLoop UI, `speakloop-ui/docs/design/screens/` (feat/ui) | Project's own work |
| Simulator footage (`public/sim.mp4`) | Screen recording of the SpeakLoop Alexa+ simulator from the earlier demo (`video/out/speakloop_demo.mp4`, 0:20–2:12), sped up 7× | Project's own work |
| SpeakLoop logo (`public/logo.svg`) | `speakloop/assets/logo.svg` | Project's own work |

Benchmark figures on screen come verbatim from `benchmarks/RESULTS.md` (feat/phoneme): L2-ARCTIC, Vietnamese L1
speakers, held-out THV + TLV, same 100 utterances (3,200 annotated phones). SpeakLoop default P 0.589 / R 0.533 /
F1 0.560 vs Whisper-small transcript diff P 0.615 / R 0.219 / F1 0.323. mcp-lite-browser size: 8,627 B min+gzip
(mcp-lite-browser CHANGELOG).

"Alexa", "Amazon Bedrock" and "Whisper" are named only to describe the platform and the benchmark baseline.
