"""Sound Graph + FSRS scheduling, with a controllable clock and an in-memory SQLite DB."""
from datetime import datetime, timedelta, timezone

import pytest
from fsrs import Rating

from speakloop.memory import SoundGraph

T0 = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
ED_T = {"op": "delete", "target": "t", "position": "coda", "prev": "k", "morpheme": "-ed", "word": "walked"}


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, **kw):
        self.t = self.t + timedelta(**kw)


@pytest.fixture
def clk():
    return Clock()


@pytest.fixture
def g(clk):
    return SoundGraph(":memory:", clock=clk)


def test_vi_pack_is_installed(g):
    assert "vi" in g.packs and "ed_t_after_voiceless" in g.pack("vi").sound_ids()
    with pytest.raises(KeyError, match="no installed L1 pack"):
        g.pack("xx")


@pytest.mark.parametrize("correct,score,stab,want", [
    (False, None, None, Rating.Again), (False, 0.99, 50, Rating.Again),
    (True, 0.5, None, Rating.Hard), (True, None, None, Rating.Good),
    (True, 0.97, 1.0, Rating.Good), (True, 0.97, 5.0, Rating.Easy),
])
def test_rating_for(correct, score, stab, want):
    assert SoundGraph.rating_for(correct, score, stab) == want


def test_new_learner_gets_common_l1_sound(g):
    d = g.next_drill("new")
    assert d["reason"] == "new" and d["sound_id"] == g.pack("vi").sounds[0]["id"]
    assert len(d["minimal_pairs"]) == 3 and d["pack"].startswith("l1-vi@")
    assert g.get_weak_sounds("new")["weak_sounds"] == []
    assert g.progress_summary("new")["attempts"] == 0


def test_error_is_classified_counted_and_graphed(g):
    out = g.record_attempt("a", errors=[ED_T])
    assert [r["sound_id"] for r in out["recorded"]] == ["ed_t_after_voiceless"]
    assert out["recorded"][0]["rating"] == "Again" and out["unclassified"] == []
    edges = g.confusions("a")
    assert edges[0]["target"] == "t" and edges[0]["realized"] == "∅" and edges[0]["sound_id"] == "ed_t_after_voiceless"
    weak = g.get_weak_sounds("a")["weak_sounds"]
    assert weak[0]["sound_id"] == "ed_t_after_voiceless" and "t→∅" in weak[0]["confusions"]


def test_unclassified_errors_are_kept_but_not_reviewed(g):
    out = g.record_attempt("a", errors=[{"op": "substitute", "target": "q", "realized": "x"}])
    assert out["recorded"] == [] and len(out["unclassified"]) == 1
    assert g.confusions("a")[0]["sound_id"] is None


def test_duplicate_errors_in_one_utterance_review_once(g):
    out = g.record_attempt("a", errors=[ED_T, dict(ED_T, word="talked")], sound_id="ed_t_after_voiceless", correct=False)
    assert len(out["recorded"]) == 1
    assert g.confusions("a")[0]["count"] == 2


def test_missed_sound_is_due_soon_and_drilled_first(g, clk):
    g.record_attempt("a", sound_id="th_voiceless", correct=True)
    g.record_attempt("a", errors=[ED_T])
    node = {n["sound_id"]: n for n in g.nodes("a")}
    miss_due = datetime.fromisoformat(node["ed_t_after_voiceless"]["due"])
    hit_due = datetime.fromisoformat(node["th_voiceless"]["due"])
    # FSRS learning steps: both new cards come back within minutes; the miss is never later.
    assert miss_due - T0 <= timedelta(minutes=10) and miss_due <= hit_due
    assert node["ed_t_after_voiceless"]["priority"] > node["th_voiceless"]["priority"]
    clk.advance(minutes=15)
    d = g.next_drill("a")
    assert d["reason"] == "due" and d["sound_id"] == "ed_t_after_voiceless"


def test_correct_reviews_grow_stability_and_push_due_out(g, clk):
    dues, stabs = [], []
    for _ in range(5):
        r = g.record_attempt("a", sound_id="plural_s", correct=True)["recorded"][0]
        dues.append(datetime.fromisoformat(r["due"])); stabs.append(r["stability_days"])
        clk.t = dues[-1] + timedelta(minutes=1)  # review when due
    assert stabs == sorted(stabs) and stabs[-1] > stabs[0]
    gaps = [b - a for a, b in zip(dues, dues[1:])]
    assert gaps[-1] > gaps[0] and gaps[-1] >= timedelta(days=1)


def test_not_due_falls_back_to_weakest_then_new(g, clk):
    g.record_attempt("a", sound_id="final_l", correct=False)
    g.record_attempt("a", sound_id="final_l", correct=False)  # card now in relearning, due in minutes
    g.record_attempt("a", sound_id="sh_s", correct=True)
    # right after the reviews nothing is due yet: the weakest sound is picked
    d = g.next_drill("a")
    assert d["reason"] == "weakest" and d["sound_id"] == "final_l"


def test_minimal_pairs_rotate_with_attempts(g):
    first = g.next_drill("a")["minimal_pairs"]
    g.record_attempt("a", sound_id=g.next_drill("a")["sound_id"], correct=False)
    second = g.next_drill("a")["minimal_pairs"]
    assert first != second and first[1] == second[0]


def test_error_counts_decay_with_half_life(g, clk):
    for _ in range(4):
        g.record_attempt("a", sound_id="z_devoicing", correct=False)
    before = g.nodes("a")[0]["error_rate"]
    g.record_attempt("a", sound_id="z_devoicing", correct=True)
    clk.advance(days=42)  # two half-lives: old misses weigh a quarter
    g.record_attempt("a", sound_id="z_devoicing", correct=True)
    after = g.nodes("a")[0]["error_rate"]
    assert before > 0.7 and after < 0.6
    assert SoundGraph._decay(8, T0.isoformat(), T0 + timedelta(days=21)) == pytest.approx(4)


def test_record_attempt_validation(g):
    with pytest.raises(ValueError, match="unknown sound_id"):
        g.record_attempt("a", sound_id="nope", correct=True)
    with pytest.raises(ValueError, match="correct is required"):
        g.record_attempt("a", sound_id="plural_s")
    with pytest.raises(KeyError):
        g.record_attempt("a", sound_id="plural_s", correct=True, l1="zz")


def test_practised_counts_as_correct_except_flagged(g):
    out = g.record_attempt("a", errors=[ED_T], practised=["ed_t_after_voiceless", "plural_s", "bogus"])
    got = {(r["sound_id"], r["correct"]) for r in out["recorded"]}
    assert got == {("ed_t_after_voiceless", False), ("plural_s", True)}


def test_progress_summary_trend_and_mastery(g, clk):
    clk.t = T0 - timedelta(days=6)
    for _ in range(3):
        g.record_attempt("a", sound_id="th_voiced", correct=False)
    clk.t = T0
    for _ in range(3):
        g.record_attempt("a", sound_id="th_voiced", correct=True)
    p = g.progress_summary("a", days=7)
    assert p["attempts"] == 6 and p["accuracy"] == 0.5
    t = p["trends"][0]
    assert t["sound_id"] == "th_voiced" and t["early_accuracy"] == 0 and t["late_accuracy"] == 1 and t["delta"] == 1
    assert "Most improved" in p["speech"]
    assert g.progress_summary("a", days=1)["attempts"] == 3


def test_state_persists_in_sqlite_file(tmp_path, clk):
    db = str(tmp_path / "sg.db")
    SoundGraph(db, clock=clk).record_attempt("p", sound_id="initial_p", correct=False)
    g2 = SoundGraph(db, clock=clk)
    assert g2.nodes("p")[0]["sound_id"] == "initial_p" and g2.export_graph("p")["nodes"]
