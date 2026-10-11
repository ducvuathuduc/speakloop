---
name: l1-vi
description: Vietnamese-L1 pronunciation pack for SpeakLoop. Use when coaching a Vietnamese speaker of English, when assess_pronunciation returns l1_findings, or when the learner asks why a sound is hard. Explains which English sounds Vietnamese speakers tend to drop or swap (final -ed/-s, TH, final clusters, final stops and L, SH/S, Z/S, initial P, vowel length, word stress), why their first language causes it, and which minimal pairs to drill.
license: MIT
metadata:
  speakloop_pack: pack.json
  rules: rules.yaml
  mcp_server: speakloop
  l1: vi
  target_language: en-US
  version: 1.1.0
---

# Vietnamese speakers of English: sound pack

One pack, two data files, both loaded by the code (edit them here and the engine and
the coach change together):

- `rules.yaml` turns a raw **phone-level event** from the phoneme scorer
  (`speakloop.phoneme.assess`, MCP tool `assess_pronunciation`) into a teachable
  finding: `rule_id`, `word`, `description_en` / `description_vi`, `tip_en` / `tip_vi`,
  and `sound_id`, the Sound Graph node it belongs to.
- `pack.json` (schema `speakloop.l1-pack/v1`) lists each **sound** as a node in the
  learner's Sound Graph, with `detect` rules, `why_l1`, `tip_en` / `tip_l1`,
  `speech_hint` (how to name the sound out loud; never read IPA aloud) and `drills`
  (minimal pairs `[target, typical mishearing]`, words, a sentence).

## How to coach with it

1. **Hear the attempt.** When the card sends audio, call `assess_pronunciation`
   (reference text + WAV). The scorer hears the learner's *phones*, not words, so it
   catches the dropped /t/ in *walked* that a transcript hides.
2. **One finding per turn.** `l1_findings[0]` is the first in the utterance. Say it in
   one sentence, naming the word ("In *walked*, the T at the end went missing"), then
   give its tip (`tip_vi` only if the learner is stuck or speaking Vietnamese).
3. **Drill it.** Call `start_pair_drill` with `focus` = the finding's `rule_id` (or
   `node` = a `sound_id`). With neither, it picks the sound the FSRS schedule says is due.
   Say the target word, then the mishearing, then ask the learner to say the target.
4. **Remember it.** `assess_pronunciation` with a `learner_id` records misses in the
   Sound Graph; for a drill result call `record_attempt` (`sound_id`, `correct`).
   `next_drill`, `get_weak_sounds` and `progress_summary` read the same graph.
5. **Never claim certainty.** The scorer reports what an open phoneme model heard; it
   can be wrong, especially on noisy audio. If the learner disagrees, replay and move on.
   Per-pattern accuracy on real Vietnamese speakers (L2-ARCTIC) is in
   `benchmarks/RESULTS.md`; phrase low-precision patterns as "it sounded like…".

## Patterns covered (rules.yaml)

| rule_id | Pattern | Example | Sound node |
|---|---|---|---|
| VN-ED-DROP | past-tense -ed dropped | walked → walk | ed_t_after_voiceless / ed_d_after_voiced |
| VN-ED-DROP-SYLLABLE | -ted/-ded syllable dropped | wanted → want | – |
| VN-S-DROP | plural / 3sg / possessive -s dropped | books → book | plural_s |
| VN-CLUSTER-REDUCTION | consonant cluster reduced | most → mos | coda_cluster |
| VN-FINAL-CONSONANT-DROP | final consonant dropped/unreleased | cat → ca | final_stop / final_l |
| VN-TH-STOP / VN-DH-STOP | /θ ð/ → /t d s z/ | think → tink | th_voiceless / th_voiced |
| VN-SH-S, VN-CH-SH | /ʃ/ → /s/, /tʃ/ → /ʃ/ | she → see | sh_s / – |
| VN-FINAL-DEVOICING | voiced final made voiceless | bad → bat | z_devoicing (for /z/) |
| VN-VOWEL-LENGTH | long/short vowel swap | sheep ↔ ship | – |
| VN-N-L | /n/–/l/ swap (Northern accents) | night → light | – |
| VN-EPENTHESIS | extra vowel after final consonant | bus → bus-uh | – |
| VN-WORD-STRESS (experimental) | stress on the wrong syllable | phoTOgraph | – |

## Adding an L1 pack

Copy `skills/l1-template/`, rename the folder `l1-<code>`, fill `pack.json`, and
optionally add a `rules.yaml` with the same `when:` fields (`error_type`, `expected`,
`heard`, `position`, `in_cluster`, `word_regex`). Validate and install with
`python -m speakloop.skillpacks validate skills/l1-<code>`; the server lists it as an
`l1` option and serves it as `skill://l1-<code>/SKILL.md`.
