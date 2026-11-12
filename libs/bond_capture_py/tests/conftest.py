import json
from datetime import date, time
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "capture"
TODAY = date(2026, 11, 11)  # a Wednesday; the date the fixtures were written for
EOD = time(17, 0)


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text())


class FakeLlm:
    """An ``LlmClient`` that replays one answer (or raises) and records every call."""

    def __init__(self, answer=None, raises: Exception | None = None):
        self.answer, self.raises, self.calls = answer, raises, []

    def complete_json(self, system, user, schema, timeout_s):
        self.calls.append({"system": system, "user": user, "schema": schema, "timeout_s": timeout_s})
        if self.raises is not None:
            raise self.raises
        return self.answer


def model_item(**over) -> dict:
    """One valid task item in the model's flat shape; keyword arguments override fields."""
    item = {"kind": "task", "title": "Call Sam", "date": "2026-11-12", "time": None, "due_defaulted": False,
            "priority": None, "all_day": False, "end_date": None, "end_time": None, "links": [],
            "confidence": 0.9}
    item.update(over)
    return item


def event_item(**over) -> dict:
    return model_item(**{"kind": "event", "title": "Lunch", "date": "2026-11-12", "all_day": True, **over})


def run(answer, text="Call Sam tomorrow", **kw):
    """``parse_capture`` over a fake model answer, with the usual arguments."""
    from bond_capture_py import parse_capture

    args = {"user_id": "u1", "today": TODAY, "time_zone": "America/Denver", "end_of_day": EOD,
            "llm": FakeLlm(answer)}
    args.update(kw)
    return parse_capture(text, **args)
