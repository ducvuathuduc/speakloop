"""End-to-end test with real wav2vec2 weights. Slow (model load) — run with ``pytest -m slow``.

Uses SPEAKLOOP_PHONEME_MODEL (default lv-60); set SPEAKLOOP_PHONEME_DTYPE=bfloat16 on small machines.
"""

from pathlib import Path
import shutil

import pytest

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not shutil.which("espeak-ng"), reason="espeak-ng not installed"),
]

FIXTURE = Path(__file__).parent / "fixtures" / "espeak_she_walked.wav"


def test_assess_espeak_fixture_end_to_end():
    pytest.importorskip("transformers")
    from speakloop.phoneme import assess

    out = assess(str(FIXTURE), "She walked to the shops.")
    ov = out["overall"]
    assert [w["word"] for w in out["words"]] == ["She", "walked", "to", "the", "shops"]
    assert ov["phones"] == len(out["phones"]) > 10
    assert ov["accuracy"] is not None and 0 <= ov["accuracy"] <= 100
    assert ov["recognised_ipa"]
    # synthetic native-like speech: most phones should pass
    assert ov["phone_error_rate"] < 0.5
    for p in out["phones"]:
        assert p["start"] is None or p["end"] >= p["start"]


def test_assess_accepts_bytes_and_flags_wrong_text():
    pytest.importorskip("transformers")
    from speakloop.phoneme import assess

    good = assess(FIXTURE.read_bytes(), "She walked to the shops.")
    bad = assess(FIXTURE.read_bytes(), "Think of zebras going north.")
    assert bad["overall"]["accuracy"] < good["overall"]["accuracy"]
