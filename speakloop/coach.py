"""Learner memory and coaching logic (state that persists across sessions).

SQLite keeps, per learner: goal (target score, exam date), every scored
attempt, and a spaced-repetition queue of words whose sounds they dropped.
The coach uses that history to plan each day's session.
"""

from __future__ import annotations

import json
import os
import random
import sqlite3
import threading
import uuid
from dataclasses import replace
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .content import DRILL_BY_ID, FEATURE_TIPS, TASK_LABELS, TASK_TYPES, Drill, drills_of
from .scoring import AttemptScore, score_attempt

DEFAULT_TZ = "Asia/Ho_Chi_Minh"

SCHEMA = """
CREATE TABLE IF NOT EXISTS learners (
    id TEXT PRIMARY KEY,
    name TEXT,
    target_score INTEGER,
    exam_date TEXT,
    timezone TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id TEXT,
    drill_id TEXT,
    task_type TEXT,
    overall INTEGER, content INTEGER, fluency INTEGER, pronunciation INTEGER,
    weak_features TEXT,
    transcript TEXT,
    day TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS review_items (
    learner_id TEXT,
    word TEXT,
    feature TEXT,
    interval_days INTEGER,
    ease REAL,
    due TEXT,
    lapses INTEGER,
    PRIMARY KEY (learner_id, word)
);
CREATE TABLE IF NOT EXISTS routines (
    learner_id TEXT PRIMARY KEY,
    time_local TEXT,
    days TEXT,
    minutes INTEGER
);
CREATE TABLE IF NOT EXISTS active_drills (
    drill_id TEXT PRIMARY KEY,
    learner_id TEXT,
    payload TEXT,
    created_at TEXT
);
"""


class Coach:
    def __init__(self, db_path: str | None = None, clock=None):
        self.db_path = db_path or os.environ.get("SPEAKLOOP_DB", "speakloop.db")
        self._lock = threading.Lock()
        self._clock = clock  # callable returning aware datetime (tests)
        self._db = sqlite3.connect(self.db_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)
        self._db.commit()

    # ------------------------------------------------------------------ utils
    def now(self, tz: str = DEFAULT_TZ) -> datetime:
        if self._clock:
            return self._clock().astimezone(ZoneInfo(tz))
        return datetime.now(ZoneInfo(tz))

    def today(self, tz: str = DEFAULT_TZ) -> date:
        return self.now(tz).date()

    def _q(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            cur = self._db.execute(sql, args)
            rows = cur.fetchall()
            self._db.commit()
            return rows

    # --------------------------------------------------------------- learners
    def ensure_learner(self, learner_id: str, name: str | None = None) -> dict:
        rows = self._q("SELECT * FROM learners WHERE id=?", (learner_id,))
        if not rows:
            self._q(
                "INSERT INTO learners (id, name, target_score, exam_date, timezone, created_at) VALUES (?,?,?,?,?,?)",
                (learner_id, name or learner_id, None, None, DEFAULT_TZ, self.now().isoformat()),
            )
            rows = self._q("SELECT * FROM learners WHERE id=?", (learner_id,))
        elif name and rows[0]["name"] != name:
            self._q("UPDATE learners SET name=? WHERE id=?", (name, learner_id))
            rows = self._q("SELECT * FROM learners WHERE id=?", (learner_id,))
        return dict(rows[0])

    def set_goal(self, learner_id: str, target_score: int | None = None, exam_date: str | None = None,
                 name: str | None = None) -> dict:
        learner = self.ensure_learner(learner_id, name)
        if target_score is not None:
            if not 10 <= int(target_score) <= 90:
                raise ValueError("target_score must be between 10 and 90")
            self._q("UPDATE learners SET target_score=? WHERE id=?", (int(target_score), learner_id))
        if exam_date:
            date.fromisoformat(exam_date)  # validate
            self._q("UPDATE learners SET exam_date=? WHERE id=?", (exam_date, learner_id))
        return self.profile(learner_id) | {"updated": True, "name": learner["name"] if not name else name}

    def profile(self, learner_id: str) -> dict:
        learner = self.ensure_learner(learner_id)
        today = self.today(learner["timezone"])
        rows = self._q(
            "SELECT task_type, AVG(overall) avg, COUNT(*) n FROM attempts WHERE learner_id=? GROUP BY task_type",
            (learner_id,),
        )
        by_task = {r["task_type"]: {"average": round(r["avg"]), "attempts": r["n"]} for r in rows}
        total = sum(v["attempts"] for v in by_task.values())
        recent = self._q(
            "SELECT overall FROM attempts WHERE learner_id=? ORDER BY id DESC LIMIT 10", (learner_id,)
        )
        estimate = round(sum(r["overall"] for r in recent) / len(recent)) if recent else None
        days_left = None
        if learner["exam_date"]:
            days_left = (date.fromisoformat(learner["exam_date"]) - today).days
        due = self._q(
            "SELECT COUNT(*) c FROM review_items WHERE learner_id=? AND due<=?", (learner_id, today.isoformat())
        )[0]["c"]
        return {
            "learner_id": learner_id,
            "name": learner["name"],
            "target_score": learner["target_score"],
            "exam_date": learner["exam_date"],
            "days_until_exam": days_left,
            "estimated_score": estimate,
            "total_attempts": total,
            "streak_days": self.streak(learner_id),
            "by_task": by_task,
            "weak_features": self.weak_features(learner_id),
            "review_due": due,
        }

    def streak(self, learner_id: str) -> int:
        days = {r["day"] for r in self._q("SELECT DISTINCT day FROM attempts WHERE learner_id=?", (learner_id,))}
        d = self.today()
        if d.isoformat() not in days:
            d -= timedelta(days=1)
        n = 0
        while d.isoformat() in days:
            n += 1
            d -= timedelta(days=1)
        return n

    def weak_features(self, learner_id: str, last_n: int = 20) -> list[dict]:
        rows = self._q(
            "SELECT weak_features FROM attempts WHERE learner_id=? ORDER BY id DESC LIMIT ?", (learner_id, last_n)
        )
        counts: dict[str, int] = {}
        for r in rows:
            for f in json.loads(r["weak_features"] or "[]"):
                counts[f] = counts.get(f, 0) + 1
        ranked = sorted(counts.items(), key=lambda kv: -kv[1])
        return [{"feature": f, "label": FEATURE_TIPS[f]["label"], "count": c} for f, c in ranked if f in FEATURE_TIPS]

    # ----------------------------------------------------------------- drills
    def _pick(self, learner_id: str, task_type: str | None, focus: str | None) -> Drill:
        if task_type and task_type not in TASK_TYPES:
            raise ValueError(f"task_type must be one of {', '.join(TASK_TYPES)}")
        if not task_type:
            task_type = self._weakest_task(learner_id)
        pool = drills_of(task_type)
        if focus:
            focused = [d for d in pool if focus in d.features]
            pool = focused or pool
        done = {r["drill_id"] for r in self._q("SELECT drill_id FROM attempts WHERE learner_id=?", (learner_id,))}
        fresh = [d for d in pool if d.id not in done]
        rng = random.Random(f"{learner_id}-{len(done)}")
        return rng.choice(fresh or pool)

    def _weakest_task(self, learner_id: str) -> str:
        rows = {r["task_type"]: r["avg"] for r in self._q(
            "SELECT task_type, AVG(overall) avg FROM attempts WHERE learner_id=? GROUP BY task_type", (learner_id,))}
        untried = [t for t in TASK_TYPES if t not in rows]
        if untried:
            return untried[0]
        return min(rows, key=rows.get)

    def start_drill(self, learner_id: str, task_type: str | None = None, focus: str | None = None) -> dict:
        self.ensure_learner(learner_id)
        drill = self._pick(learner_id, task_type, focus)
        return self._activate(learner_id, drill)

    def _activate(self, learner_id: str, drill: Drill) -> dict:
        session_drill_id = f"{drill.id}:{uuid.uuid4().hex[:8]}"
        payload = {
            "base_id": drill.id, "task_type": drill.task_type, "prompt": drill.prompt,
            "reference": drill.reference, "features": list(drill.features),
            "keywords": list(drill.keywords), "accepted": list(drill.accepted), "chart": drill.chart,
        }
        self._q("INSERT INTO active_drills VALUES (?,?,?,?)",
                (session_drill_id, learner_id, json.dumps(payload), self.now().isoformat()))
        show_text = drill.task_type in ("read_aloud",)
        return {
            "drill_id": session_drill_id,
            "task_type": drill.task_type,
            "task_label": TASK_LABELS.get(drill.task_type, "Review"),
            "prompt": drill.prompt,
            # Text the learner sees on screen. Repeat Sentence is audio-only: the device speaks it.
            "display_text": drill.reference if show_text else None,
            "speak_text": drill.reference if drill.task_type in ("repeat_sentence", "review") else
                          (drill.prompt if drill.task_type == "answer_short_question" else None),
            "chart": drill.chart,
            "features": list(drill.features),
            "time_limit_seconds": {"read_aloud": 40, "repeat_sentence": 15, "answer_short_question": 10,
                                   "describe_image": 40, "review": 20}.get(drill.task_type, 30),
        }

    def _load_active(self, drill_id: str) -> tuple[str, Drill]:
        rows = self._q("SELECT * FROM active_drills WHERE drill_id=?", (drill_id,))
        if rows:
            p = json.loads(rows[0]["payload"])
            d = Drill(p["base_id"], p["task_type"], p["prompt"], p["reference"], tuple(p["features"]),
                      tuple(p["accepted"]), tuple(p["keywords"]), p["chart"])
            return rows[0]["learner_id"], d
        base = DRILL_BY_ID.get(drill_id.split(":")[0])
        if not base:
            raise ValueError(f"Unknown drill_id {drill_id!r}. Start a drill first.")
        return "", base

    # ---------------------------------------------------------------- attempts
    def submit_attempt(self, learner_id: str, drill_id: str, transcript: str,
                       duration_seconds: float | None = None) -> dict:
        self.ensure_learner(learner_id)
        _, drill = self._load_active(drill_id)
        scoring_drill = drill if drill.task_type != "review" else replace(drill, task_type="repeat_sentence")
        # Word-list reviews are about articulation, not pace: skip the fluency maths.
        pace = None if drill.task_type == "review" else duration_seconds
        score: AttemptScore = score_attempt(scoring_drill, transcript, pace)
        now = self.now()
        self._q(
            "INSERT INTO attempts (learner_id, drill_id, task_type, overall, content, fluency, pronunciation,"
            " weak_features, transcript, day, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (learner_id, drill.id, drill.task_type, score.overall, score.content, score.fluency,
             score.pronunciation, json.dumps(score.weak_features), transcript, now.date().isoformat(),
             now.isoformat()),
        )
        self._update_reviews(learner_id, drill, score)
        self._q("DELETE FROM active_drills WHERE drill_id=?", (drill_id,))
        tips = [{"feature": f, **FEATURE_TIPS[f]} for f in score.weak_features if f in FEATURE_TIPS][:3]
        return {
            "drill_id": drill_id,
            "task_type": drill.task_type,
            "task_label": TASK_LABELS.get(drill.task_type, "Review"),
            "transcript": transcript,
            "reference": drill.reference,
            "score": score.to_dict(),
            "tips": tips,
            "streak_days": self.streak(learner_id),
        }

    def _update_reviews(self, learner_id: str, drill: Drill, score: AttemptScore) -> None:
        today = self.today()
        missed = {i.expected: i.feature for i in score.issues if i.feature}
        for word, feature in missed.items():
            self._q(
                "INSERT INTO review_items VALUES (?,?,?,?,?,?,?) ON CONFLICT(learner_id, word) DO UPDATE SET "
                "interval_days=0, ease=MAX(1.3, ease-0.2), due=excluded.due, lapses=lapses+1, feature=excluded.feature",
                (learner_id, word, feature, 0, 2.5, (today + timedelta(days=1)).isoformat(), 1),
            )
        if drill.task_type == "review":
            not_said = {i.expected for i in score.issues}
            for word in drill.keywords:
                if word in not_said:
                    continue
                if word in missed:
                    continue
                row = self._q("SELECT * FROM review_items WHERE learner_id=? AND word=?", (learner_id, word))
                if not row:
                    continue
                r = row[0]
                interval = 1 if r["interval_days"] == 0 else max(2, round(r["interval_days"] * r["ease"]))
                self._q("UPDATE review_items SET interval_days=?, due=? WHERE learner_id=? AND word=?",
                        (interval, (today + timedelta(days=interval)).isoformat(), learner_id, word))

    # ----------------------------------------------------------------- review
    def due_reviews(self, learner_id: str, limit: int = 5) -> list[dict]:
        today = self.today().isoformat()
        rows = self._q(
            "SELECT word, feature, lapses, due FROM review_items WHERE learner_id=? AND due<=? "
            "ORDER BY lapses DESC, due LIMIT ?", (learner_id, today, limit))
        return [dict(r) | {"tip": FEATURE_TIPS.get(r["feature"], {}).get("en")} for r in rows]

    def start_review(self, learner_id: str, limit: int = 5) -> dict:
        items = self.due_reviews(learner_id, limit)
        if not items:
            return {"drill_id": None, "items": [], "message": "No words are due for review today."}
        words = [i["word"] for i in items]
        sentence = "Say these words clearly: " + ", ".join(words) + "."
        drill = Drill(f"review-{len(words)}", "review", "Say each word clearly, finishing the last sound.",
                      " ".join(words), tuple(sorted({i["feature"] for i in items})), keywords=tuple(words))
        out = self._activate(learner_id, drill)
        out.update({"items": items, "display_text": "  ·  ".join(words), "speak_text": sentence,
                    "task_label": "Sound Review"})
        return out

    # ------------------------------------------------------------------- plan
    def plan_today(self, learner_id: str, minutes: int = 15) -> dict:
        prof = self.profile(learner_id)
        minutes = max(5, min(int(minutes), 60))
        steps: list[dict] = []
        budget = minutes
        if prof["review_due"]:
            steps.append({"step": "review", "tool": "start_sound_review", "minutes": 3,
                          "why": f"{prof['review_due']} word(s) from earlier sessions are due for review."})
            budget -= 3
        weak = prof["weak_features"]
        focus = weak[0]["feature"] if weak and weak[0]["feature"] in (
            "final_s", "final_ed", "th", "clusters", "final_consonant") else None
        order = sorted(TASK_TYPES, key=lambda t: prof["by_task"].get(t, {"average": 0})["average"])
        cost = {"read_aloud": 4, "repeat_sentence": 2, "answer_short_question": 1, "describe_image": 4}
        i = 0
        while budget >= 1 and i < 12:
            t = order[i % len(order)]
            if cost[t] <= budget:
                avg = prof["by_task"].get(t)
                why = "Not tried yet." if not avg else f"Your average here is {avg['average']}."
                if focus and t in ("read_aloud", "repeat_sentence"):
                    why += f" Focus: {FEATURE_TIPS[focus]['label']}."
                steps.append({"step": t, "tool": "start_drill", "minutes": cost[t], "task_type": t,
                              "focus": focus if t in ("read_aloud", "repeat_sentence") else None, "why": why})
                budget -= cost[t]
            i += 1
        intensity = "normal"
        if prof["days_until_exam"] is not None:
            if prof["days_until_exam"] <= 7:
                intensity = "exam week: full-length practice, rest the night before"
            elif prof["days_until_exam"] <= 30:
                intensity = "final month: daily practice"
        return {"learner_id": learner_id, "minutes": minutes, "intensity": intensity,
                "focus_feature": focus, "steps": steps, "profile": prof}

    # ----------------------------------------------------------------- report
    def progress(self, learner_id: str, days: int = 14) -> dict:
        prof = self.profile(learner_id)
        since = (self.today() - timedelta(days=days - 1)).isoformat()
        rows = self._q(
            "SELECT day, AVG(overall) avg, COUNT(*) n FROM attempts WHERE learner_id=? AND day>=? GROUP BY day ORDER BY day",
            (learner_id, since))
        series = [{"day": r["day"], "average": round(r["avg"]), "attempts": r["n"]} for r in rows]
        gap = None
        if prof["target_score"] and prof["estimated_score"]:
            gap = prof["target_score"] - prof["estimated_score"]
        return {"profile": prof, "daily": series, "gap_to_target": gap}

    # --------------------------------------------------------------- routine
    DAY_CODES = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")

    def set_routine(self, learner_id: str, time_local: str, days: list[str] | None = None, minutes: int = 10) -> dict:
        self.ensure_learner(learner_id)
        hh, mm = (int(x) for x in time_local.split(":"))
        if not (0 <= hh < 24 and 0 <= mm < 60):
            raise ValueError("time_local must be HH:MM (24h)")
        days = [d.upper()[:2] for d in (days or list(self.DAY_CODES))]
        if any(d not in self.DAY_CODES for d in days):
            raise ValueError("days must be like MO, TU, WE, TH, FR, SA, SU")
        self._q("INSERT INTO routines VALUES (?,?,?,?) ON CONFLICT(learner_id) DO UPDATE SET "
                "time_local=excluded.time_local, days=excluded.days, minutes=excluded.minutes",
                (learner_id, f"{hh:02d}:{mm:02d}", ",".join(days), int(minutes)))
        return self.routine(learner_id)

    def routine(self, learner_id: str) -> dict | None:
        rows = self._q("SELECT * FROM routines WHERE learner_id=?", (learner_id,))
        return dict(rows[0]) if rows else None

    def routine_ics(self, learner_id: str) -> str:
        """RFC 5545 calendar with a recurring practice event + alarm (importable into any calendar)."""
        r = self.routine(learner_id)
        if not r:
            raise ValueError("No routine set")
        learner = self.ensure_learner(learner_id)
        start = self.today()
        hh, mm = r["time_local"].split(":")
        dtstart = f"{start.strftime('%Y%m%d')}T{hh}{mm}00"
        end_min = int(hh) * 60 + int(mm) + r["minutes"]
        dtend = f"{start.strftime('%Y%m%d')}T{end_min // 60 % 24:02d}{end_min % 60:02d}00"
        lines = [
            "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//SpeakLoop//Speaking coach//EN", "CALSCALE:GREGORIAN",
            "BEGIN:VEVENT",
            f"UID:speakloop-{learner_id}@speakloop.local",
            f"DTSTAMP:{self.now().astimezone(ZoneInfo('UTC')).strftime('%Y%m%dT%H%M%SZ')}",
            f"DTSTART;TZID={learner['timezone']}:{dtstart}",
            f"DTEND;TZID={learner['timezone']}:{dtend}",
            f"RRULE:FREQ=WEEKLY;BYDAY={r['days']}",
            f"SUMMARY:SpeakLoop practice ({r['minutes']} min)",
            "DESCRIPTION:Say: \"Alexa\\, open SpeakLoop\" and \"let's practise\".",
            "BEGIN:VALARM", "TRIGGER:-PT5M", "ACTION:DISPLAY", "DESCRIPTION:SpeakLoop practice in 5 minutes", "END:VALARM",
            "END:VEVENT", "END:VCALENDAR",
        ]
        return "\r\n".join(lines) + "\r\n"
