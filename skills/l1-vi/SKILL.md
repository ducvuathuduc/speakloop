---
name: l1-vi
description: Vietnamese-L1 pronunciation pack for SpeakLoop. Use when coaching a Vietnamese speaker of English, to explain which English sounds they are likely to drop or swap (final -ed/-s, TH, final clusters, final stops and L, SH/S, Z/S, initial P), why their first language causes it, and which minimal pairs to drill.
license: MIT
metadata:
  speakloop_pack: pack.json
  l1: vi
  target_language: en-US
  version: 1.0.0
---

# Vietnamese speakers of English: sound pack

This skill is data first. `pack.json` (schema `speakloop.l1-pack/v1`) lists each
sound as a node in the learner's Sound Graph, with:

- `detect`: phone-level rules (`delete` / `substitute` / `insert`, with position and
  context) that map a phoneme-alignment error onto this sound;
- `why_l1`: the one-line reason Vietnamese makes this hard (say it once, kindly);
- `tip_en` / `tip_l1`: a mouth-position tip in English and Vietnamese;
- `speech_hint`: how to name the sound out loud on a voice device (never read IPA aloud);
- `drills`: minimal pairs (target, typical mishearing), words and a sentence.

## How to coach with it

1. After an attempt, call `record_attempt` with the sound ids the scorer flagged
   (or the raw phone errors; the server classifies them with this pack).
2. Call `next_drill` to get the sound that the FSRS schedule says is due, and run
   its minimal pairs: say the target word, then the mishearing, then ask the learner
   to say the target.
3. Use `tip_l1` only when the learner is stuck or answers in Vietnamese.
4. `progress_summary` gives the week in one sentence for the voice reply.

Install or validate with `python -m speakloop.skillpacks validate skills/l1-vi`.
