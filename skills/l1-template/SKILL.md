---
name: l1-xx
description: TEMPLATE. Replace xx with the ISO 639-1 code of the learner's first language and describe which English sounds speakers of that language find hard. Copy this folder to skills/l1-<code>/, edit pack.json, then run `python -m speakloop.skillpacks validate skills/l1-<code>`.
license: MIT
metadata:
  speakloop_pack: pack.json
  l1: xx
  target_language: en-US
  version: 0.1.0
---

# <Language> speakers of English: sound pack (template)

Fill `pack.json` with one entry per sound. Each needs an `id` (snake_case, unique),
at least one `detect` rule, a tip in English and in the learner's language, a
`speech_hint` that a voice assistant can say aloud (no IPA symbols), and at least two
minimal pairs. Cite where each pattern comes from in `sources`.
