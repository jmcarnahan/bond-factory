import dataclasses
import json

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
    LlmInvalid,
    LlmUnavailable,
    TaskCandidate,
)


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


def test_phrase_set_is_present_and_well_formed():
    rows = [json.loads(line) for line in (FIXTURES / "phrases.jsonl").read_text().splitlines()]
    assert [r["id"] for r in rows] == list(range(1, 61))
    assert {r["lang"] for r in rows} == {"en", "es"}
    assert sum(r["cat"] == "either" for r in rows) >= 5  # honest "a person could not decide" labels


def test_error_codes():
    assert CaptureDenied().status == 429 and CaptureDenied().code == "capture_denied"
    assert CaptureError("text_required").status == 422 and CaptureError("text_too_long").status == 422
    assert LlmUnavailable().code == "model_unavailable" and LlmInvalid().code == "invalid_output"
    assert all(issubclass(c, CaptureError) for c in (LlmUnavailable, LlmInvalid, CaptureDenied))
