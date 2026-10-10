# Sound patterns SpeakLoop flags

Vietnamese is a tonal, mostly monosyllabic language whose syllables end in a small
set of unreleased consonants. Learners therefore tend to:

| Pattern | Example (expected → heard) | Feature id |
|---|---|---|
| Drop plural / 3rd-person -s | books → book, needs → need | `final_s` |
| Drop past-tense -ed | asked → ask, moved → move | `final_ed` |
| Replace /θ/ /ð/ with /t/ /d/ /s/ | think → tink, three → tree, the → de | `th` |
| Reduce consonant clusters | most → mos, tests → tess | `clusters` |
| Leave final consonant unreleased | week → wee, hall → haw | `final_consonant` |

Speech recognisers "hear" these as a different word, so a substitution in the
transcript that matches one of these shapes is treated as a pronunciation slip,
and the word goes into the learner's spaced-repetition review queue.
