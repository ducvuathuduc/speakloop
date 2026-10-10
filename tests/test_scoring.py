from speakloop.content import DRILL_BY_ID
from speakloop.scoring import classify_error, score_attempt, tokenize


def test_tokenize_numbers_and_case():
    assert tokenize("The 12 Books!") == ["the", "twelve", "books"]


def test_classify_vietnamese_l1_patterns():
    assert classify_error("books", "book") == "final_s"
    assert classify_error("asked", "ask") == "final_ed"
    assert classify_error("moved", "move") == "final_ed"
    assert classify_error("think", "tink") == "th"
    assert classify_error("three", "tree") == "th"
    assert classify_error("most", "mos") == "final_consonant"
    assert classify_error("library", "library") is None
    assert classify_error("library", "banana") is None


def test_perfect_repeat_sentence_scores_high():
    d = DRILL_BY_ID["rs-02"]
    s = score_attempt(d, d.reference, duration_seconds=3.2)
    assert s.content == 90 and s.pronunciation == 90
    assert s.overall >= 85
    assert s.weak_features == []


def test_dropped_endings_are_detected():
    d = DRILL_BY_ID["rs-02"]  # "Three of the students asked for more time."
    s = score_attempt(d, "tree of the student ask for more time", duration_seconds=3.0)
    feats = {i.feature for i in s.issues if i.feature}
    assert {"th", "final_s", "final_ed"} <= feats
    assert s.pronunciation < 60
    assert s.overall < score_attempt(d, d.reference, 3.0).overall


def test_fillers_and_slow_pace_hurt_fluency():
    d = DRILL_BY_ID["rs-01"]
    good = score_attempt(d, d.reference, duration_seconds=2.8)
    bad = score_attempt(d, "um the the library uh opens at eight on weekdays", duration_seconds=9)
    assert bad.fillers == 2 and bad.restarts == 1
    assert bad.fluency < good.fluency


def test_short_question_accepts_digits_and_flags_near_miss():
    d = DRILL_BY_ID["asq-02"]
    assert score_attempt(d, "12", 1).correct is True
    assert score_attempt(d, "twelve months", 1).correct is True
    assert score_attempt(d, "ten", 1).correct is False


def test_describe_image_keyword_coverage():
    d = DRILL_BY_ID["di-01"]
    s = score_attempt(d, "The chart shows study minutes. Saturday is the highest and Wednesday is the lowest.", 8)
    assert "saturday" in s.covered_keywords and "weekend" in s.missed_keywords
    assert 10 < s.content < 90
