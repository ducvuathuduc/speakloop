"""Seed a demo learner with 6 earlier practice days (real scoring, simulated dates).

Usage: python scripts/seed_demo.py [db_path] [learner_id]
Creates learner 'lan' (target 79, exam ~9 weeks out) whose earlier attempts dropped
-s/-ed endings and TH sounds, so today's session shows streak, due reviews and a plan.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from speakloop.coach import Coach  # noqa: E402
from speakloop.content import DRILL_BY_ID  # noqa: E402

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
db = sys.argv[1] if len(sys.argv) > 1 else "speakloop.db"
learner = sys.argv[2] if len(sys.argv) > 2 else "lan"
now = datetime.now(TZ).replace(hour=20, minute=0, second=0, microsecond=0)

clock_t = {"t": now}
coach = Coach(db, clock=lambda: clock_t["t"])
coach.set_goal(learner, 79, (now + timedelta(days=63)).date().isoformat(), name="Lan")

# (days ago, drill id, transcript, seconds)
history = [
    (6, "rs-02", "tree of the student ask for more time", 3.4),
    (6, "asq-03", "ice", 1.5),
    (5, "ra-01", "most student tink that learning a language is about memorising word in fact the fastest learner "
                 "practise speaking every day record themselves and listen carefully to the sound they miss", 16),
    (4, "rs-08", "the result will be publish next mont", 3.6),
    (4, "asq-01", "architect", 1.8),
    (3, "rs-06", "they watch the match together last night", 3.0),
    (3, "di-02", "the chart compare the way people travel motorbike are the most popular about seventy percent buses and cars are less", 14),
    (2, "rs-05", "most of the test are marked within a week", 3.1),
    (1, "ra-03", "scientists have found that a short walk after lunch helps the brain stay focus the effect last for several hours "
                 "and works for people of all ages", 12.5),
    (1, "rs-03", "please hand in your reports by thursday afternoon", 3.3),
]
for days_ago, drill_id, transcript, secs in history:
    clock_t["t"] = now - timedelta(days=days_ago)
    d = coach._activate(learner, DRILL_BY_ID[drill_id])
    coach.submit_attempt(learner, d["drill_id"], transcript, secs)

clock_t["t"] = now
p = coach.profile(learner)
print(f"seeded {learner}: {p['total_attempts']} attempts, streak {p['streak_days']}, estimate {p['estimated_score']}, "
      f"review due {p['review_due']}, weak {[w['feature'] for w in p['weak_features']]}")
