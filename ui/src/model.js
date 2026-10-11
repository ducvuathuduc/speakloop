// Pure helpers that turn assess() output into what the cards draw. No DOM here: unit-tested.

export const STATUS = {
  ok: { symbol: "✓", label: "heard as expected" },
  substitution: { symbol: "≈", label: "came out as another sound" },
  deletion: { symbol: "∅", label: "sound missing" },
  insertion: { symbol: "+", label: "extra sound" },
};

export const statusOf = (p) => (p?.error_type ? p.error_type : "ok");
const clean = (w) => String(w || "").toLowerCase().replace(/[^a-z0-9']/g, "");

/** Group phones under words. Uses words[].phone_range when present, else time overlap. */
export function groupWords(a) {
  const phones = a?.phones || [];
  const words = a?.words?.length ? a.words : [{ word: a?.reference_text || "", start: 0, end: Infinity }];
  return words.map((w, wi) => {
    let idx;
    if (Array.isArray(w.phone_range)) {
      idx = [];
      for (let i = w.phone_range[0]; i < w.phone_range[1]; i++) idx.push(i);
    } else if (Array.isArray(w.phones) && typeof w.phones[0] === "number") {
      idx = w.phones;
    } else {
      idx = phones.map((p, i) => [p, i]).filter(([p]) => p.start >= (w.start ?? 0) - 1e-3 && p.end <= (w.end ?? Infinity) + 1e-3).map(([, i]) => i);
    }
    const ps = idx.map((i) => ({ ...phones[i], index: i }));
    const errors = ps.filter((p) => p.error_type);
    return { text: w.word ?? w.text ?? "", start: w.start, end: w.end, phones: ps, errors, index: wi };
  });
}

/** Index of the phone under the playhead at time t (seconds), or -1. */
export function activePhoneIndex(phones, t) {
  if (!phones?.length || t == null) return -1;
  let best = -1;
  for (let i = 0; i < phones.length; i++) {
    if (t >= phones[i].start - 1e-6) best = i; else break;
  }
  if (best >= 0 && t > phones[best].end + 0.25 && best === phones.length - 1) return -1;
  return best;
}

export const ipaSlash = (s) => `/${s}/`;

/** One sentence, learner language: the single most important thing that happened. */
export function headline(a) {
  const words = groupWords(a);
  const f = a?.l1_findings?.[0];
  const w = f ? words.find((x) => clean(x.text) === clean(f.word)) : words.find((x) => x.errors.length);
  const err = f && w ? (w.phones.find((p) => p.index === f.position) || w.errors[0]) : w?.errors[0];
  if (!w || !err) return { en: "Every sound came through clearly.", vi: "Mọi âm đều rõ ràng.", word: null, phone: null };
  const word = clean(w.text);
  if (err.error_type === "deletion") return { en: `The ${ipaSlash(err.expected)} in “${word}” went missing.`, vi: f?.description_vi, word, phone: err };
  if (err.error_type === "substitution") return { en: `“${word}” used ${ipaSlash(err.ipa)} instead of ${ipaSlash(err.expected)}.`, vi: f?.description_vi, word, phone: err };
  return { en: `An extra ${ipaSlash(err.ipa)} slipped into “${word}”.`, vi: f?.description_vi, word, phone: err };
}

export const pct = (x) => Math.round(Math.max(0, Math.min(1, x || 0)) * 100);

export function fmtClock(sec) {
  const s = Math.max(0, Math.round(sec || 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** SVG ring geometry: stroke-dasharray/offset for a progress ring. */
export function ringDash(value, r) {
  const c = 2 * Math.PI * r;
  return { c, offset: c * (1 - Math.max(0, Math.min(1, value || 0))) };
}

/** Speech line for voice-only parity (no symbols, no pipes). */
export function spokenSummary(a) {
  const h = headline(a);
  return h.en.replace(/[“”]/g, "")
    .replace(/\b(The|the|An extra|an extra) \/(.*?)\//g, (_, art, ipa) => `${art} ${ipa} sound`)
    .replace(/\/(.*?)\//g, "the $1 sound");
}

/** "final /t/ missing" style caption for the focus word's first error. */
export function focusNote(w) {
  const e = w?.errors?.[0];
  if (!e) return "";
  const pos = e.index === w.phones[w.phones.length - 1]?.index ? "final " : e.index === w.phones[0]?.index ? "first " : "";
  if (e.error_type === "deletion") return `${pos}/${e.expected}/ missing`;
  if (e.error_type === "substitution") return `/${e.ipa}/ for /${e.expected}/`;
  return `extra /${e.ipa}/`;
}

/** What was actually heard for a word, as /ipa/ (deleted phones dropped). */
export const heardIpa = (w) => ipaSlash((w?.phones || []).filter((p) => p.error_type !== "deletion" && p.ipa).map((p) => p.ipa).join(""));
