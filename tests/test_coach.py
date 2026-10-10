from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from speakloop.coach import Coach

TZ = ZoneInfo("Asia/Ho_Chi_Minh")


class Clock:
    def __init__(self):
        self.t = datetime(2026, 10, 10, 20, 0, tzinfo=TZ)

    def __call__(self):
        return self.t


@pytest.fixture
def coach(tmp_path):
    clock = Clock()
    c = Coach(str(tmp_path / "c.db"), clock=clock)
    c.clock = clock
    return c


def test_goal_and_profile(coach):
    p = coach.set_goal("lan", 65, "2026-12-15", name="Lan")
    assert p["target_score"] == 65 and p["days_until_exam"] == 66 and p["name"] == "Lan"
    with pytest.raises(ValueError):
        coach.set_goal("lan", 95)


def test_full_loop_persists_across_sessions(coach):
    d = coach.start_drill("lan", "repeat_sentence", focus="th")
    assert d["display_text"] is None and d["speak_text"]  # audio-only task
    r = coach.submit_attempt("lan", d["drill_id"], "tree of the student ask for more time"
                             if "Three" in d["speak_text"] else "uh " + d["speak_text"].lower(), 3.0)
    assert r["score"]["overall"] >= 10
    # Next day: streak continues, missed sounds come back for review.
    coach.clock.t += timedelta(days=1)
    d2 = coach.start_drill("lan", "read_aloud")
    coach.submit_attempt("lan", d2["drill_id"], d2["display_text"], 14)
    prof = coach.profile("lan")
    assert prof["total_attempts"] == 2 and prof["streak_days"] == 2


def test_spaced_repetition_and_plan(coach):
    from speakloop.content import DRILL_BY_ID
    drill = coach._activate("lan", DRILL_BY_ID["rs-02"])
    coach.submit_attempt("lan", drill["drill_id"], "tree of the student ask for more time", 3)
    assert coach.due_reviews("lan") == []  # due tomorrow, not today
    coach.clock.t += timedelta(days=1)
    due = {i["word"] for i in coach.due_reviews("lan")}
    assert {"three", "students", "asked"} <= due
    plan = coach.plan_today("lan", 10)
    assert plan["steps"][0]["step"] == "review"
    assert sum(s["minutes"] for s in plan["steps"]) <= 10
    rv = coach.start_review("lan")
    r = coach.submit_attempt("lan", rv["drill_id"], " ".join(i["word"] for i in rv["items"]), 4)
    assert r["score"]["content"] == 90
    assert coach.due_reviews("lan") == []  # rescheduled into the future


def test_weakest_task_is_picked(coach):
    for t in ("read_aloud", "repeat_sentence", "answer_short_question"):
        d = coach.start_drill("lan", t)
        coach.submit_attempt("lan", d["drill_id"], d["display_text"] or d["speak_text"] or "", 5)
    assert coach.start_drill("lan")["task_type"] == "describe_image"


def test_unknown_drill(coach):
    with pytest.raises(ValueError):
        coach.submit_attempt("lan", "nope", "hello")


def test_routine_and_ics(coach):
    r = coach.set_routine("lan", "20:30", ["mo", "we", "fr"], 15)
    assert r == {"learner_id": "lan", "time_local": "20:30", "days": "MO,WE,FR", "minutes": 15}
    ics = coach.routine_ics("lan")
    assert "RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR" in ics and "DTSTART;TZID=Asia/Ho_Chi_Minh:20261010T203000" in ics
    assert "DTEND;TZID=Asia/Ho_Chi_Minh:20261010T204500" in ics and ics.endswith("\r\n")
    with pytest.raises(ValueError):
        coach.set_routine("lan", "25:00")
