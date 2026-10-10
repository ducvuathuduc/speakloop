"""Drill bank for SpeakLoop.

Every item is original content written for this project. Items are tagged with
the pronunciation features they exercise, chosen around the sounds Vietnamese
speakers of English most often drop or substitute (final consonants, -s/-ed
endings, /θ/ and /ð/, consonant clusters, word stress).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

TaskType = Literal["read_aloud", "repeat_sentence", "answer_short_question", "describe_image"]

TASK_TYPES: tuple[TaskType, ...] = (
    "read_aloud",
    "repeat_sentence",
    "answer_short_question",
    "describe_image",
)

TASK_LABELS: dict[str, str] = {
    "read_aloud": "Read Aloud",
    "repeat_sentence": "Repeat Sentence",
    "answer_short_question": "Answer Short Question",
    "describe_image": "Describe Image",
}

# Seconds a learner gets to answer, used for the on-screen timer and fluency maths.
TASK_TIME_LIMIT: dict[str, int] = {
    "read_aloud": 40,
    "repeat_sentence": 15,
    "answer_short_question": 10,
    "describe_image": 40,
}


@dataclass(frozen=True)
class Drill:
    id: str
    task_type: TaskType
    prompt: str            # what the coach says / shows
    reference: str         # expected answer text (or model answer)
    features: tuple[str, ...] = ()
    accepted: tuple[str, ...] = ()   # alternative accepted answers (short questions)
    keywords: tuple[str, ...] = ()   # content words expected in describe_image
    chart: dict | None = field(default=None, hash=False, compare=False)


DRILLS: tuple[Drill, ...] = (
    # ---------------- Read Aloud ----------------
    Drill(
        "ra-01", "read_aloud",
        "Read the passage aloud.",
        "Most students think that learning a language is about memorising words. "
        "In fact, the fastest learners practise speaking every day, record themselves, "
        "and listen carefully to the sounds they missed.",
        ("th", "final_s", "final_ed", "clusters"),
    ),
    Drill(
        "ra-02", "read_aloud",
        "Read the passage aloud.",
        "Ho Chi Minh City has grown quickly over the last thirty years. "
        "New bridges, metro lines and parks have changed the way people travel, "
        "but traffic is still one of the biggest challenges for the city.",
        ("th", "final_s", "final_ed", "clusters"),
    ),
    Drill(
        "ra-03", "read_aloud",
        "Read the passage aloud.",
        "Scientists have found that a short walk after lunch helps the brain stay focused. "
        "The effect lasts for several hours and works for people of all ages.",
        ("final_s", "final_ed", "clusters", "final_consonant"),
    ),
    Drill(
        "ra-04", "read_aloud",
        "Read the passage aloud.",
        "Small businesses often depend on social media to reach customers. "
        "Those that answer messages quickly and post useful content tend to build stronger relationships.",
        ("th", "final_s", "clusters"),
    ),
    # ---------------- Repeat Sentence ----------------
    Drill("rs-01", "repeat_sentence", "Listen and repeat the sentence.",
          "The library opens at eight on weekdays.", ("final_s", "final_consonant")),
    Drill("rs-02", "repeat_sentence", "Listen and repeat the sentence.",
          "Three of the students asked for more time.", ("th", "final_ed", "final_s")),
    Drill("rs-03", "repeat_sentence", "Listen and repeat the sentence.",
          "Please hand in your reports by Thursday afternoon.", ("th", "final_s")),
    Drill("rs-04", "repeat_sentence", "Listen and repeat the sentence.",
          "The lecture was moved to the main hall.", ("final_ed", "final_consonant")),
    Drill("rs-05", "repeat_sentence", "Listen and repeat the sentence.",
          "Most of the tests are marked within a week.", ("clusters", "final_ed", "final_s")),
    Drill("rs-06", "repeat_sentence", "Listen and repeat the sentence.",
          "They watched the match together last night.", ("th", "final_ed", "clusters")),
    Drill("rs-07", "repeat_sentence", "Listen and repeat the sentence.",
          "Each group needs to choose a leader.", ("final_s", "final_consonant")),
    Drill("rs-08", "repeat_sentence", "Listen and repeat the sentence.",
          "The results will be published next month.", ("final_ed", "clusters", "th")),
    # ---------------- Answer Short Question ----------------
    Drill("asq-01", "answer_short_question",
          "What do you call a person who designs buildings?", "architect"),
    Drill("asq-02", "answer_short_question",
          "How many months are there in a year?", "twelve", accepted=("12",)),
    Drill("asq-03", "answer_short_question",
          "What do we call frozen water?", "ice"),
    Drill("asq-04", "answer_short_question",
          "Which instrument is used to look at stars?", "telescope"),
    Drill("asq-05", "answer_short_question",
          "What is the opposite of 'ancient'?", "modern"),
    Drill("asq-06", "answer_short_question",
          "If today is Tuesday, what day was it yesterday?", "monday"),
    # ---------------- Describe Image ----------------
    Drill(
        "di-01", "describe_image",
        "Describe the bar chart: daily study minutes by weekday.",
        "The bar chart shows how many minutes a student studied each day. "
        "The highest value was on Saturday at about ninety minutes, while Wednesday was the lowest at around twenty. "
        "Overall, the student studied more at the weekend than on weekdays.",
        ("final_s", "th", "final_ed"),
        keywords=("chart", "minutes", "saturday", "highest", "wednesday", "lowest", "weekend", "weekdays"),
        chart={
            "title": "Daily study minutes",
            "labels": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
            "values": [45, 35, 20, 40, 30, 90, 75],
            "unit": "min",
        },
    ),
    Drill(
        "di-02", "describe_image",
        "Describe the bar chart: how people commute in a city.",
        "The chart compares the ways people travel to work. "
        "Motorbikes are by far the most popular, used by around seventy percent of commuters. "
        "Buses and cars are much less common, and only a small share of people walk or cycle.",
        ("final_s", "clusters", "th"),
        keywords=("chart", "motorbikes", "popular", "percent", "buses", "cars", "walk", "cycle"),
        chart={
            "title": "Commute mode share (%)",
            "labels": ["Motorbike", "Bus", "Car", "Walk", "Bicycle"],
            "values": [70, 12, 9, 5, 4],
            "unit": "%",
        },
    ),
)

DRILL_BY_ID: dict[str, Drill] = {d.id: d for d in DRILLS}


def drills_of(task_type: str) -> list[Drill]:
    return [d for d in DRILLS if d.task_type == task_type]


FEATURE_TIPS: dict[str, dict[str, str]] = {
    "final_s": {
        "label": "Final -s / -es",
        "en": "Finish plural and verb endings: say the hiss or buzz at the end (books, needs).",
        "vi": "Đừng nuốt âm cuối -s/-es: kéo dài tiếng 'xì' hoặc 'dz' ở cuối từ (books, needs).",
    },
    "final_ed": {
        "label": "Past tense -ed",
        "en": "Pronounce -ed as /t/, /d/ or /ɪd/ (asked /t/, moved /d/, needed /ɪd/).",
        "vi": "Đọc rõ đuôi -ed thành /t/, /d/ hoặc /ɪd/ (asked /t/, moved /d/, needed /ɪd/).",
    },
    "th": {
        "label": "TH sounds /θ/ /ð/",
        "en": "Put your tongue between your teeth for 'th' (think, three, the) instead of /t/, /d/ or /s/.",
        "vi": "Đặt đầu lưỡi giữa hai hàm răng khi đọc 'th' (think, three, the), đừng đọc thành /t/, /d/ hay /s/.",
    },
    "clusters": {
        "label": "Consonant clusters",
        "en": "Keep every consonant in groups like -st, -sts, -nth, -ct (most, tests, month, effect).",
        "vi": "Giữ đủ các phụ âm trong cụm như -st, -sts, -nth, -ct (most, tests, month, effect).",
    },
    "final_consonant": {
        "label": "Final consonants",
        "en": "Release the last consonant clearly (week, hall, opens) — Vietnamese syllables often stop it.",
        "vi": "Bật rõ phụ âm cuối (week, hall, opens) — tiếng Việt thường không bật âm cuối.",
    },
    "fluency": {
        "label": "Fluency",
        "en": "Keep a steady pace with no restarts; a short pause at commas is fine, 'uh' and 'um' are not.",
        "vi": "Giữ nhịp đều, không lặp lại hay dừng giữa chừng; ngắt nhẹ ở dấu phẩy, tránh 'ờ', 'à'.",
    },
    "content": {
        "label": "Content",
        "en": "Cover every word (read aloud / repeat) or every key point (describe image).",
        "vi": "Nói đủ các từ (đọc/nhắc lại câu) hoặc đủ ý chính (mô tả biểu đồ).",
    },
}
