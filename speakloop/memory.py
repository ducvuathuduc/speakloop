"""Learner memory: a per-learner phoneme error graph with FSRS spaced repetition.

Two structures live in SQLite next to the coach tables:

* **Sound nodes** (``sg_nodes``): one row per (learner, sound id from the L1 pack). Each row
  holds an FSRS card (py-fsrs, ``fsrs.Scheduler``) that decides when the sound is next due,
  plus recency-weighted counts of correct / incorrect attempts.
* **Confusion edges** (``sg_edges``): target phone -> what was actually produced
  (``t -> ∅`` for a deletion, ``θ -> t`` for a substitution, ``∅ -> ə`` for an insertion), with
  counts. Together with the nodes this is the learner's "Sound Graph".

FSRS rating from an attempt: wrong -> Again; right but shaky (score < 0.8) -> Hard;
right -> Good; right with score >= 0.95 and the sound already stable -> Easy.

Priority for "what to drill next" (documented so it can be checked):
    priority = p_error + 0.5 * (1 - R)
where p_error is the posterior mean of a Beta(1,1) prior updated with exponentially decayed
counts (half-life 21 days) and R is FSRS retrievability now. Due cards always come first.
"""

from __future__ import annotations

import json
import math
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from fsrs import Card, Rating, Scheduler

from .skillpacks import SoundPack, classify_error, discover_packs

HALF_LIFE_DAYS = 21.0
EMPTY = "∅"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sg_nodes (
  learner_id TEXT NOT NULL, sound_id TEXT NOT NULL, l1 TEXT NOT NULL,
  card_json TEXT NOT NULL, due_ts TEXT NOT NULL,
  n_correct REAL NOT NULL DEFAULT 0, n_wrong REAL NOT NULL DEFAULT 0,
  attempts INTEGER NOT NULL DEFAULT 0, last_ts TEXT,
  PRIMARY KEY (learner_id, sound_id)
);
CREATE TABLE IF NOT EXISTS sg_attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, learner_id TEXT NOT NULL, sound_id TEXT NOT NULL,
  correct INTEGER NOT NULL, rating INTEGER NOT NULL, word TEXT, score REAL, ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sg_attempts_learner_ts ON sg_attempts(learner_id, ts);
CREATE TABLE IF NOT EXISTS sg_edges (
  learner_id TEXT NOT NULL, op TEXT NOT NULL, target TEXT NOT NULL, realized TEXT NOT NULL,
  sound_id TEXT, count INTEGER NOT NULL DEFAULT 0, last_ts TEXT,
  PRIMARY KEY (learner_id, op, target, realized)
);
"""


def _utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class SoundGraph:
    def __init__(self, db_path: str = ":memory:", packs: dict[str, SoundPack] | None = None,
                 clock: Callable[[], datetime] | None = None, scheduler: Scheduler | None = None):
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)
        self._lock = threading.Lock()
        self.packs = packs if packs is not None else discover_packs()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.scheduler = scheduler or Scheduler(enable_fuzzing=False)

    # ------------------------------------------------------------ helpers
    def now(self) -> datetime:
        return _utc(self.clock())

    def pack(self, l1: str = "vi") -> SoundPack:
        if l1 not in self.packs:
            raise KeyError(f"no installed L1 pack for '{l1}' (installed: {sorted(self.packs)})")
        return self.packs[l1]

    def _q(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            cur = self._db.execute(sql, args)
            rows = cur.fetchall()
            self._db.commit()
            return rows

    def _node(self, learner_id: str, sound_id: str) -> sqlite3.Row | None:
        r = self._q("SELECT * FROM sg_nodes WHERE learner_id=? AND sound_id=?", (learner_id, sound_id))
        return r[0] if r else None

    @staticmethod
    def _decay(n: float, last_ts: str | None, now: datetime) -> float:
        if not last_ts or not n:
            return n or 0.0
        days = max(0.0, (now - datetime.fromisoformat(last_ts)).total_seconds() / 86400)
        return n * math.pow(0.5, days / HALF_LIFE_DAYS)

    @staticmethod
    def rating_for(correct: bool, score: float | None, stability: float | None) -> Rating:
        if not correct:
            return Rating.Again
        if score is not None and score < 0.8:
            return Rating.Hard
        if score is not None and score >= 0.95 and (stability or 0) >= 3:
            return Rating.Easy
        return Rating.Good

    # ------------------------------------------------------------ writes
    def _review(self, learner_id: str, l1: str, sound_id: str, correct: bool, score: float | None,
                word: str | None, now: datetime) -> dict:
        row = self._node(learner_id, sound_id)
        card = Card.from_json(row["card_json"]) if row else Card(due=now)
        rating = self.rating_for(correct, score, card.stability)
        card, _log = self.scheduler.review_card(card, rating, review_datetime=now)
        n_c = self._decay(row["n_correct"], row["last_ts"], now) if row else 0.0
        n_w = self._decay(row["n_wrong"], row["last_ts"], now) if row else 0.0
        n_c, n_w = n_c + (1 if correct else 0), n_w + (0 if correct else 1)
        attempts = (row["attempts"] if row else 0) + 1
        self._q(
            "INSERT INTO sg_nodes(learner_id,sound_id,l1,card_json,due_ts,n_correct,n_wrong,attempts,last_ts) "
            "VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(learner_id,sound_id) DO UPDATE SET "
            "card_json=excluded.card_json,due_ts=excluded.due_ts,n_correct=excluded.n_correct,"
            "n_wrong=excluded.n_wrong,attempts=excluded.attempts,last_ts=excluded.last_ts",
            (learner_id, sound_id, l1, card.to_json(), _utc(card.due).isoformat(), n_c, n_w, attempts, now.isoformat()))
        self._q("INSERT INTO sg_attempts(learner_id,sound_id,correct,rating,word,score,ts) VALUES(?,?,?,?,?,?,?)",
                (learner_id, sound_id, int(correct), int(rating), word, score, now.isoformat()))
        return {"sound_id": sound_id, "correct": correct, "rating": rating.name, "due": _utc(card.due).isoformat(),
                "stability_days": round(card.stability or 0, 2)}

    def _edge(self, learner_id: str, err: dict, sound_id: str | None, now: datetime) -> None:
        op = err.get("op")
        target = err.get("target") or EMPTY
        realized = EMPTY if op == "delete" else (err.get("realized") or EMPTY)
        self._q("INSERT INTO sg_edges(learner_id,op,target,realized,sound_id,count,last_ts) VALUES(?,?,?,?,?,1,?) "
                "ON CONFLICT(learner_id,op,target,realized) DO UPDATE SET count=count+1,last_ts=excluded.last_ts,"
                "sound_id=COALESCE(excluded.sound_id,sound_id)",
                (learner_id, op, target, realized, sound_id, now.isoformat()))

    def record_attempt(self, learner_id: str, *, sound_id: str | None = None, correct: bool | None = None,
                       errors: list[dict] | None = None, practised: list[str] | None = None,
                       word: str | None = None, score: float | None = None, l1: str = "vi",
                       at: datetime | None = None) -> dict:
        """Record one attempt.

        * ``sound_id`` + ``correct``: a direct result for one sound (e.g. a minimal-pair drill).
        * ``errors``: phone-level errors from the scorer; each is classified with the L1 pack and
          counts as a wrong attempt on its sound, and is added to the confusion graph.
        * ``practised``: sound ids that were exercised in the utterance and NOT flagged (correct).
        """
        pack = self.pack(l1)
        now = _utc(at) if at else self.now()
        known = set(pack.sound_ids())
        reviews: list[dict] = []
        unclassified: list[dict] = []
        wrong: set[str] = set()
        for err in errors or []:
            sid = err.get("sound_id") or classify_error(pack, err)
            self._edge(learner_id, err, sid, now)
            if sid and sid in known:
                if sid not in wrong:
                    wrong.add(sid)
                    reviews.append(self._review(learner_id, l1, sid, False, score, err.get("word") or word, now))
            else:
                unclassified.append(err)
        if sound_id is not None:
            if sound_id not in known:
                raise ValueError(f"unknown sound_id '{sound_id}' for pack {pack.id}")
            if correct is None:
                raise ValueError("correct is required with sound_id")
            if not (sound_id in wrong and not correct):
                reviews.append(self._review(learner_id, l1, sound_id, bool(correct), score, word, now))
        for sid in practised or []:
            if sid in known and sid not in wrong and sid != sound_id:
                reviews.append(self._review(learner_id, l1, sid, True, score, word, now))
        return {"learner_id": learner_id, "recorded": reviews, "unclassified": unclassified}

    # ------------------------------------------------------------ reads
    def _node_view(self, row: sqlite3.Row, now: datetime, pack: SoundPack) -> dict:
        card = Card.from_json(row["card_json"])
        n_c = self._decay(row["n_correct"], row["last_ts"], now)
        n_w = self._decay(row["n_wrong"], row["last_ts"], now)
        p_err = (n_w + 1) / (n_c + n_w + 2)
        r = self.scheduler.get_card_retrievability(card, now)
        due = _utc(card.due)
        s = pack.sound(row["sound_id"]) or {}
        return {
            "sound_id": row["sound_id"], "label": s.get("label"), "speech_hint": s.get("speech_hint"),
            "category": s.get("category"), "attempts": row["attempts"],
            "error_rate": round(p_err, 3), "retrievability": round(r, 3),
            "stability_days": round(card.stability or 0, 2), "due": due.isoformat(), "is_due": due <= now,
            "priority": round(p_err + 0.5 * (1 - r), 3),
        }

    def nodes(self, learner_id: str, l1: str = "vi") -> list[dict]:
        pack, now = self.pack(l1), self.now()
        return [self._node_view(r, now, pack)
                for r in self._q("SELECT * FROM sg_nodes WHERE learner_id=? AND l1=?", (learner_id, l1))]

    def confusions(self, learner_id: str, limit: int = 10) -> list[dict]:
        return [dict(r) for r in self._q(
            "SELECT op,target,realized,sound_id,count FROM sg_edges WHERE learner_id=? ORDER BY count DESC, last_ts DESC LIMIT ?",
            (learner_id, limit))]

    def get_weak_sounds(self, learner_id: str, limit: int = 3, l1: str = "vi") -> dict:
        ns = sorted(self.nodes(learner_id, l1), key=lambda n: (-n["error_rate"], -n["attempts"]))
        weak = [n for n in ns if n["error_rate"] > 0.5][:limit]
        edges = self.confusions(learner_id, 50)
        for n in weak:
            n["confusions"] = [f"{e['target']}→{e['realized']}" for e in edges if e["sound_id"] == n["sound_id"]][:3]
        if weak:
            names = [n["speech_hint"] for n in weak]
            speech = "Your trickiest sounds right now: " + (", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else names[0]) + "."
        else:
            speech = "No weak sounds yet. Do a few attempts and I'll map them."
        return {"kind": "weak_sounds", "learner_id": learner_id, "weak_sounds": weak, "speech": speech}

    def next_drill(self, learner_id: str, l1: str = "vi", pairs: int = 3) -> dict:
        pack, now = self.pack(l1), self.now()
        ns = self.nodes(learner_id, l1)
        due = sorted([n for n in ns if n["is_due"]], key=lambda n: -n["priority"])
        seen = {n["sound_id"] for n in ns}
        if due:
            pick, reason = due[0], "due"
        else:
            unseen = [s for s in pack.sounds if s["id"] not in seen]
            weak = sorted([n for n in ns if n["error_rate"] > 0.5], key=lambda n: -n["priority"])
            if weak:
                pick, reason = weak[0], "weakest"
            elif unseen:
                pick, reason = {"sound_id": unseen[0]["id"]}, "new"
            else:
                pick, reason = min(ns, key=lambda n: n["due"]), "earliest"
        s = pack.sound(pick["sound_id"])
        att = int(pick.get("attempts") or 0)
        mp = s["drills"]["minimal_pairs"]
        chosen = [mp[(att + i) % len(mp)] for i in range(min(pairs, len(mp)))]
        why = {"due": "it's due for review", "weakest": "it's your weakest sound",
               "new": f"it's common for {pack.data['l1_name']} speakers",
               "earliest": "it's the next one coming up"}[reason]
        speech = (f"Let's practise {s['speech_hint']}, because {why}. "
                  f"Say: {chosen[0][0]}. Not {chosen[0][1]}. {chosen[0][0]}.")
        return {
            "kind": "sound_drill", "learner_id": learner_id, "sound_id": s["id"], "label": s["label"],
            "reason": reason, "tip_en": s["tip_en"], "tip_l1": s["tip_l1"], "why_l1": s["why_l1"],
            "minimal_pairs": chosen, "words": s["drills"]["words"][:6],
            "sentence": (s["drills"].get("sentences") or [None])[0],
            "due": pick.get("due"), "speech": speech, "pack": f"{pack.id}@{pack.version}",
        }

    def progress_summary(self, learner_id: str, days: int = 7, l1: str = "vi") -> dict:
        pack, now = self.pack(l1), self.now()
        since = now - timedelta(days=days)
        mid = now - timedelta(days=days / 2)
        rows = self._q("SELECT sound_id, correct, ts FROM sg_attempts WHERE learner_id=? AND ts>=? ORDER BY ts",
                       (learner_id, since.isoformat()))
        total = len(rows)
        acc = round(sum(r["correct"] for r in rows) / total, 3) if total else None
        per: dict[str, dict[str, list[int]]] = {}
        for r in rows:
            half = "late" if datetime.fromisoformat(r["ts"]) >= mid else "early"
            per.setdefault(r["sound_id"], {"early": [], "late": []})[half].append(r["correct"])
        trends = []
        for sid, h in per.items():
            e = sum(h["early"]) / len(h["early"]) if h["early"] else None
            l_ = sum(h["late"]) / len(h["late"]) if h["late"] else None
            trends.append({"sound_id": sid, "label": (pack.sound(sid) or {}).get("label"),
                           "speech_hint": (pack.sound(sid) or {}).get("speech_hint"),
                           "attempts": len(h["early"]) + len(h["late"]),
                           "early_accuracy": None if e is None else round(e, 3),
                           "late_accuracy": None if l_ is None else round(l_, 3),
                           "delta": None if e is None or l_ is None else round(l_ - e, 3)})
        trends.sort(key=lambda t: -(t["delta"] if t["delta"] is not None else -9))
        ns = self.nodes(learner_id, l1)
        mastered = [n["sound_id"] for n in ns if n["stability_days"] >= 21 and n["error_rate"] < 0.3]
        due_now = sum(1 for n in ns if n["is_due"])
        if not total:
            speech = f"No sound practice in the last {days} days. Want a two-minute warm-up?"
        else:
            bits = [f"This week you did {total} sound attempts at {round(acc * 100)} percent."]
            up = next((t for t in trends if t["delta"] and t["delta"] > 0), None)
            if up:
                bits.append(f"Most improved: {up['speech_hint']}.")
            if due_now:
                bits.append(f"{due_now} sound{'s are' if due_now > 1 else ' is'} due for review.")
            speech = " ".join(bits)
        return {"kind": "sound_progress", "learner_id": learner_id, "days": days, "attempts": total,
                "accuracy": acc, "trends": trends, "mastered": mastered, "due_now": due_now,
                "sounds_tracked": len(ns), "speech": speech}

    def export_graph(self, learner_id: str, l1: str = "vi") -> dict[str, Any]:
        """Nodes + confusion edges, ready for a card or a JSON dump."""
        return {"nodes": self.nodes(learner_id, l1), "edges": self.confusions(learner_id, 200)}
