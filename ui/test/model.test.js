import { describe, expect, it } from "vitest";
import { assessment } from "../src/fixtures.js";
import {
  activePhoneIndex, fmtClock, focusNote, groupWords, headline, heardIpa, pct, ringDash, spokenSummary, statusOf,
} from "../src/model.js";

const P = (ipa, expected, start, end, error_type = null) => ({ ipa, expected, start, end, score: 0.9, error_type });

describe("groupWords", () => {
  it("groups phones by phone_range and keeps global indices", () => {
    const words = groupWords(assessment);
    expect(words.map((w) => w.text)).toEqual(["She", "walked", "to", "the", "shops", "yesterday."]);
    expect(words.map((w) => w.phones.length)).toEqual([2, 4, 2, 2, 4, 7]);
    const walked = words[1];
    expect(walked.phones.map((p) => p.index)).toEqual([2, 3, 4, 5]);
    expect(walked.errors).toHaveLength(1);
    expect(walked.errors[0]).toMatchObject({ expected: "t", error_type: "deletion", index: 5 });
    expect(words.flatMap((w) => w.phones).length).toBe(assessment.phones.length);
  });

  it("falls back to time overlap when phone_range is absent", () => {
    const a = {
      phones: [P("k", "k", 0.0, 0.1), P("æ", "æ", 0.1, 0.2), P(null, "t", 0.2, 0.25, "deletion"), P("s", "s", 0.4, 0.5)],
      words: [{ word: "cat", start: 0, end: 0.25 }, { word: "s", start: 0.4, end: 0.5 }],
    };
    const [cat, s] = groupWords(a);
    expect(cat.phones.map((p) => p.index)).toEqual([0, 1, 2]);
    expect(cat.errors.map((p) => p.index)).toEqual([2]);
    expect(s.phones.map((p) => p.index)).toEqual([3]);
  });

  it("accepts words[].phones as an index list", () => {
    const a = { phones: [P("a", "a", 0, 1), P("b", "b", 1, 2)], words: [{ word: "ab", phones: [1, 0] }] };
    expect(groupWords(a)[0].phones.map((p) => p.ipa)).toEqual(["b", "a"]);
  });

  it("treats a missing words list as one word spanning the reference", () => {
    const a = { reference_text: "hi", phones: [P("h", "h", 0, 1), P("aɪ", "aɪ", 1, 2)] };
    const words = groupWords(a);
    expect(words).toHaveLength(1);
    expect(words[0].text).toBe("hi");
    expect(words[0].phones).toHaveLength(2);
  });

  it("survives empty input", () => {
    expect(groupWords(undefined)).toEqual([{ text: "", start: 0, end: Infinity, phones: [], errors: [], index: 0 }]);
  });
});

describe("headline", () => {
  it("leads with the first L1 finding, not the first error in the sentence", () => {
    const h = headline(assessment);
    expect(h.word).toBe("walked");
    expect(h.en).toBe("The /t/ in “walked” went missing.");
    expect(h.vi).toMatch(/^Âm \/t\//);
    expect(h.phone.index).toBe(5);
  });

  it("uses the finding's position to pick the phone inside the word", () => {
    const a = { ...assessment, l1_findings: [{ word: "the", position: 8, description_vi: "x" }] };
    expect(headline(a).en).toBe("“the” used /d/ instead of /ð/.");
  });

  it("falls back to the first word with an error when there are no findings", () => {
    const a = { ...assessment, l1_findings: [] };
    expect(headline(a).word).toBe("walked");
    expect(headline(a).vi).toBeUndefined();
  });

  it("matches the finding word case- and punctuation-insensitively", () => {
    const a = { ...assessment, l1_findings: [{ word: "Shops!", position: 13 }] };
    expect(headline(a).en).toBe("The /s/ in “shops” went missing.");
  });

  it("describes insertions", () => {
    const a = { phones: [P("ə", null, 0, 1, "insertion"), P("s", "s", 1, 2)], words: [{ word: "school", phone_range: [0, 2] }] };
    expect(headline(a).en).toBe("An extra /ə/ slipped into “school”.");
  });

  it("praises a clean take", () => {
    const a = { phones: [P("h", "h", 0, 1)], words: [{ word: "hi", phone_range: [0, 1] }] };
    expect(headline(a)).toMatchObject({ en: "Every sound came through clearly.", word: null, phone: null });
  });

  it("produces a symbol-free spoken line for voice parity", () => {
    expect(spokenSummary(assessment)).toBe("The t sound in walked went missing.");
    expect(spokenSummary({ ...assessment, l1_findings: [{ word: "the", position: 8 }] })).toBe("the used the d sound instead of the ð sound.");
  });
});

describe("focus word captions", () => {
  const words = groupWords(assessment);
  it("names a word-final deletion and the sounds actually heard", () => {
    expect(focusNote(words[1])).toBe("final /t/ missing");
    expect(heardIpa(words[1])).toBe("/wɔːk/");
  });
  it("names a word-initial substitution", () => {
    expect(focusNote(words[3])).toBe("/d/ for /ð/");
  });
  it("is empty for a clean word", () => {
    expect(focusNote(words[0])).toBe("");
  });
});

describe("small helpers", () => {
  it("activePhoneIndex follows the playhead and clears after the last phone", () => {
    const phones = assessment.phones;
    expect(activePhoneIndex(phones, 0)).toBe(-1);
    expect(activePhoneIndex(phones, 0.33)).toBe(0);
    expect(activePhoneIndex(phones, 1.37)).toBe(8);
    expect(activePhoneIndex(phones, 2.7)).toBe(20);
    expect(activePhoneIndex(phones, 3.5)).toBe(-1);
    expect(activePhoneIndex([], 1)).toBe(-1);
    expect(activePhoneIndex(phones, null)).toBe(-1);
  });
  it("statusOf, pct, fmtClock, ringDash", () => {
    expect(statusOf({ error_type: null })).toBe("ok");
    expect(statusOf({ error_type: "deletion" })).toBe("deletion");
    expect([pct(0.424), pct(-1), pct(2), pct(undefined)]).toEqual([42, 0, 100, 0]);
    expect([fmtClock(0), fmtClock(84), fmtClock(-3)]).toEqual(["0:00", "1:24", "0:00"]);
    const { c, offset } = ringDash(0.25, 10);
    expect(c).toBeCloseTo(2 * Math.PI * 10);
    expect(offset).toBeCloseTo(c * 0.75);
  });
});
