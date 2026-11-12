import dataclasses
from datetime import date, time

import pytest
from conftest import FIXTURES, fixture

from bond_capture_py import (
    MAX_ITEMS,
    MAX_LINKS,
    MAX_TEXT,
    MODEL_SCHEMA,
    CaptureDenied,
    CaptureError,
    CaptureResult,
    EventCandidate,
    LinkCandidate,
    LlmInvalid,
    LlmUnavailable,
    TaskCandidate,
    build_prompt,
    degraded_draft,
    fence,
    parse_capture,
)


# This local mapper stands in for the mapping inside parse_capture. Delete it, and run the fixture through
# parse_capture with a fake LlmClient instead, once parse_capture exists.
def candidates_from_model_output(raw: dict) -> CaptureResult:
    """What the capture mapping does for this fixture (no resolver, no degradation)."""
    items = []
    for item in raw["items"]:
        links = tuple(LinkCandidate(text=link["text"], kind=link["kind"]) for link in item["links"])
        if item["kind"] == "task":
            items.append(TaskCandidate(title=item["title"], due_date=item["date"], due_time=item["time"],
                                       due_defaulted=item["due_defaulted"], priority=item["priority"],
                                       links=links, confidence=item["confidence"]))
        else:
            items.append(EventCandidate(title=item["title"], start_date=item["date"], start_time=item["time"],
                                        all_day=item["all_day"], end_date=item["end_date"],
                                        end_time=item["end_time"], links=links, confidence=item["confidence"]))
    return CaptureResult(items=tuple(items))


def test_to_dict_equals_the_fixture():
    result = candidates_from_model_output(fixture("model_output.json"))
    assert result.to_dict() == fixture("expected_candidates.json")
    assert list(result.to_dict()["items"][0]) == list(fixture("expected_candidates.json")["items"][0])


def test_degraded_result_wire_shape():
    draft = TaskCandidate(title="Call Sam", due_date="2026-11-11", due_defaulted=True, confidence=0.2,
                          flags=("low_confidence",), degraded=True)
    wire = CaptureResult(items=(draft,), degraded=True, reason="model_unavailable").to_dict()
    assert wire["degraded"] is True and wire["reason"] == "model_unavailable"
    assert wire["items"][0]["flags"] == ["low_confidence"] and wire["items"][0]["degraded"] is True
    assert CaptureResult().to_dict() == {"items": [], "degraded": False, "reason": None}


def test_candidates_are_frozen_and_kind_is_fixed():
    task = TaskCandidate(title="t", due_date="2026-11-11")
    with pytest.raises(dataclasses.FrozenInstanceError):
        task.title = "x"
    assert task.kind == "task" and EventCandidate(title="e", start_date="2026-11-11").kind == "event"


def test_model_schema_equals_the_fixture():
    assert MODEL_SCHEMA == fixture("schema.json")
    assert (MAX_TEXT, MAX_ITEMS, MAX_LINKS) == (500, 8, 5)
    assert MODEL_SCHEMA["properties"]["items"]["maxItems"] == MAX_ITEMS
    item = MODEL_SCHEMA["properties"]["items"]["items"]
    assert item["properties"]["links"]["maxItems"] == MAX_LINKS
    assert set(item["required"]) == set(item["properties"])


def test_phrase_set_is_present():
    lines = (FIXTURES / "phrases.jsonl").read_text().splitlines()
    assert len(lines) == 40


def test_error_codes():
    assert CaptureDenied().status == 429 and CaptureDenied().code == "capture_denied"
    assert CaptureError("text_required").status == 422 and CaptureError("text_too_long").status == 422
    assert LlmUnavailable().code == "model_unavailable" and LlmInvalid().code == "invalid_output"
    assert all(issubclass(c, CaptureError) for c in (LlmUnavailable, LlmInvalid, CaptureDenied))


def test_stubs_raise_not_implemented():
    calls = [
        lambda: build_prompt(date(2026, 11, 11), "Wednesday", "UTC", time(17, 0)),
        lambda: fence("x"),
        lambda: parse_capture("x", user_id="u", today=date(2026, 11, 11), time_zone="UTC",
                              end_of_day=time(17, 0), llm=None),
        lambda: degraded_draft("x", date(2026, 11, 11)),
    ]
    for call in calls:
        with pytest.raises(NotImplementedError):
            call()
