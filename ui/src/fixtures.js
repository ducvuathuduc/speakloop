// Fixtures that mirror the contracts in docs/UI_CONTRACT.md.
// `assessment` mocks speakloop.phoneme.assess() (being built on feat/phoneme):
//   {phones:[{ipa, expected, start, end, score, error_type}], words, l1_findings:[...], overall}
// error_type: null | "deletion" | "substitution" | "insertion". For a deletion `ipa` is null.

const P = (ipa, expected, start, end, score, error_type = null) => ({ ipa, expected, start, end, score, error_type });

export const assessment = {
  kind: "assessment",
  engine: "fixture",
  reference_text: "She walked to the shops yesterday.",
  asr_transcript: "She walked to the shops yesterday.",
  phones: [
    P("ʃ", "ʃ", 0.32, 0.44, 0.94), P("iː", "iː", 0.44, 0.58, 0.91),
    P("w", "w", 0.66, 0.74, 0.9), P("ɔː", "ɔː", 0.74, 0.92, 0.86), P("k", "k", 0.92, 1.02, 0.81), P(null, "t", 1.02, 1.06, 0.08, "deletion"),
    P("t", "t", 1.14, 1.2, 0.88), P("uː", "uː", 1.2, 1.3, 0.84),
    P("d", "ð", 1.34, 1.4, 0.31, "substitution"), P("ə", "ə", 1.4, 1.46, 0.8),
    P("ʃ", "ʃ", 1.52, 1.64, 0.93), P("ɒ", "ɒ", 1.64, 1.76, 0.85), P("p", "p", 1.76, 1.84, 0.82), P(null, "s", 1.84, 1.88, 0.11, "deletion"),
    P("j", "j", 1.96, 2.02, 0.86), P("ɛ", "ɛ", 2.02, 2.1, 0.88), P("s", "s", 2.1, 2.2, 0.9), P("t", "t", 2.2, 2.26, 0.79),
    P("ə", "ə", 2.26, 2.32, 0.83), P("d", "d", 2.32, 2.38, 0.85), P("eɪ", "eɪ", 2.38, 2.62, 0.9),
  ],
  words: [
    { word: "She", start: 0.32, end: 0.58, score: 0.93, phone_range: [0, 2] },
    { word: "walked", start: 0.66, end: 1.06, score: 0.66, phone_range: [2, 6] },
    { word: "to", start: 1.14, end: 1.3, score: 0.86, phone_range: [6, 8] },
    { word: "the", start: 1.34, end: 1.46, score: 0.55, phone_range: [8, 10] },
    { word: "shops", start: 1.52, end: 1.88, score: 0.68, phone_range: [10, 14] },
    { word: "yesterday.", start: 1.96, end: 2.62, score: 0.86, phone_range: [14, 21] },
  ],
  l1_findings: [
    { rule_id: "vn.final_ed_deletion", word: "walked", position: 5,
      description_en: "The /t/ at the end of “walked” went missing. Vietnamese has no final /kt/ cluster, so the ending is easy to drop.",
      description_vi: "Âm /t/ cuối trong “walked” bị mất. Tiếng Việt không có cụm phụ âm cuối /kt/ nên rất dễ nuốt âm này." },
    { rule_id: "vn.final_s_deletion", word: "shops", position: 13,
      description_en: "The plural /s/ in “shops” was not pronounced.",
      description_vi: "Âm /s/ số nhiều trong “shops” chưa được phát âm." },
    { rule_id: "vn.th_stopping", word: "the", position: 8,
      description_en: "“the” started with /d/ instead of /ð/.",
      description_vi: "“the” bắt đầu bằng /d/ thay vì /ð/." },
  ],
  overall: { score: 0.78, phones_correct: 18, phones_total: 21 },
  sound_graph_update: { node: "-ed after voiceless /k/", times_this_week: 3, next_review: "tomorrow" },
};

export const soundRings = {
  kind: "sound_rings",
  window_label: "This week",
  nodes: [
    { id: "ed_after_voiceless", label: "-ed endings", context_ipa: "/t/ after /k p s/", mastery: 0.42, delta_week: 0.08, due_today: true },
    { id: "final_s", label: "Final -s", context_ipa: "/s z/ word-final", mastery: 0.61, delta_week: 0.12, due_today: false },
    { id: "th_voiced", label: "Voiced th", context_ipa: "/ð/ in the, this", mastery: 0.74, delta_week: -0.03, due_today: false },
  ],
  next_session: { minutes: 2, node: "ed_after_voiceless" },
};

export const pairDrill = {
  kind: "pair_drill",
  title: "2-minute warm-up",
  focus_label: "-ed after voiceless sounds",
  instruction: "Say the highlighted word",
  step: 3, total: 8, seconds_left: 84, seconds_total: 120,
  pair: {
    a: { word: "walk", ipa: ["w", "ɔː", "k"] },
    b: { word: "walked", ipa: ["w", "ɔː", "k", "t"], diff: [3] },
    say: "b",
  },
  last_attempt: { word: "pick / picked", ok: true, note: "Clear /t/" },
};

export const listen = {
  kind: "listen",
  reference_text: "She walked to the shops yesterday.",
  hint: "Or just say it to Alexa.",
};

export const micFallback = { ...listen, mic_state: "blocked" };

export const plan = {
  kind: "plan",
  minutes: 10,
  focus_label: "-ed endings",
  steps: [
    { label: "Sound review", minutes: 2, why: "4 words are due today", tool: "start_sound_review" },
    { label: "Minimal pairs: walk / walked", minutes: 3, why: "your weakest sound this week", step: "pairs" },
    { label: "Read aloud", minutes: 5, why: "use -ed in full sentences", step: "read_aloud" },
  ],
  profile: { days_until_exam: null },
};

export const FIXTURES = { assessment, karaoke: { ...assessment, view: "sounds" }, rings: soundRings, drill: pairDrill, listen, mic: micFallback, plan };
