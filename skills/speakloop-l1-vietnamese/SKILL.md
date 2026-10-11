---
name: speakloop-l1-vietnamese
description: Explain English pronunciation errors typical of Vietnamese speakers (dropped final consonants, -s/-ed endings, cluster reduction, th→t/d, sh→s, vowel length, word stress) using phone-level findings from SpeakLoop's phoneme scorer. Use when a SpeakLoop assessment returns l1_findings, or when a Vietnamese learner asks why a sound is hard.
license: MIT
metadata:
  mcp_server: speakloop
  l1: vi
  rules: rules.yaml
---

# Vietnamese-L1 pronunciation pack

This skill pairs with `speakloop.phoneme.assess()`. The scorer hears the learner's
**phones** (not words), and `rules.yaml` in this folder maps each phone-level event
to a teachable pattern. The same file is loaded by the code, so editing a rule here
changes both what the coach says and what the engine reports.

## How to use findings

An assessment returns `l1_findings`, each with `rule_id`, `word`, `position`,
`description_en` and `description_vi`.

1. Pick **one** finding per turn: the first one is the highest-priority one in the
   utterance. Say it in one sentence, naming the word ("In *walked*, the /t/ at the
   end went missing").
2. Give the matching tip from `rules.yaml` (`tip_en`, or `tip_vi` if the learner is
   speaking Vietnamese).
3. Offer a two-word minimal pair to try (walk / walked, ship / sheep, tree / three).
4. Never claim certainty. The scorer reports what an open phoneme model heard; it can
   be wrong, especially on noisy audio. If the learner disagrees, replay and move on.

## Patterns covered

| rule_id | Pattern | Example |
|---|---|---|
| VN-ED-DROP | past-tense -ed dropped | walked → walk |
| VN-ED-DROP-SYLLABLE | -ted/-ded syllable dropped | wanted → want |
| VN-S-DROP | plural / 3sg / possessive -s dropped | books → book |
| VN-CLUSTER-REDUCTION | consonant cluster reduced | most → mos |
| VN-FINAL-CONSONANT-DROP | final consonant dropped/unreleased | cat → ca |
| VN-TH-STOP / VN-DH-STOP | /θ ð/ → /t d s z/ | think → tink |
| VN-SH-S, VN-CH-SH | /ʃ/ → /s/, /tʃ/ → /ʃ/ | she → see |
| VN-FINAL-DEVOICING | voiced final made voiceless | bad → bat |
| VN-VOWEL-LENGTH | long/short vowel swap | sheep ↔ ship |
| VN-N-L | /n/–/l/ swap (Northern accents) | night → light |
| VN-EPENTHESIS | extra vowel after final consonant | bus → bus-uh |
| VN-WORD-STRESS (experimental) | stress on the wrong syllable | phoTOgraph |

Accuracy of each pattern on real Vietnamese speakers (L2-ARCTIC) is in
`benchmarks/RESULTS.md`. Patterns with low precision there should be phrased as
"it sounded like…" rather than as a firm correction.

## Adding an L1 pack

Copy this folder, change `l1`, and write rules with the same `when:` fields
(`error_type`, `expected`, `heard`, `position`, `in_cluster`, `word_regex`).
Load it with `assess(..., rules_path="skills/<pack>/rules.yaml")`.
