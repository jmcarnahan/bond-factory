import json

import pytest
from conftest import EOD, FIXTURES, TODAY, FakeLlm, fixture, model_item, run

from bond_capture_py import RICH_MODEL_SCHEMA, build_prompt, model_schema, parse_capture

PHRASES = fixture("rich_phrases.json")


class Resolver:
    def __init__(self, rows=None):
        self.rows, self.calls = rows or {}, []

    def resolve(self, user_id, name, kind):
        self.calls.append((name, kind))
        return self.rows.get((name, kind), [])


def rich(answer, **kw):
    return run(answer, rich=True, **kw)


def test_rich_schema_matches_fixture():
    assert RICH_MODEL_SCHEMA == fixture("schema_rich.json")
    item = RICH_MODEL_SCHEMA["properties"]["items"]["items"]
    assert set(item["required"]) == set(item["properties"])
    assert {"location", "notes", "duration_minutes", "attendees"} <= set(item["properties"])
    assert model_schema(rich=True) == RICH_MODEL_SCHEMA


def test_rich_fixture_wire_round_trip():
    case = PHRASES["cases"][0]
    llm = FakeLlm(fixture(case["model_output"]))
    wire = parse_capture(case["phrase"], user_id="u1", today=TODAY, time_zone="America/Denver", end_of_day=EOD,
                         llm=llm, resolver=Resolver(), rich=True).to_dict()
    assert wire == fixture(case["expected"])
    assert llm.calls[0]["schema"] == RICH_MODEL_SCHEMA and "CAPTURE-PROMPT-V2" in llm.calls[0]["system"]


def test_rich_event_location_notes_duration():
    wire = rich(fixture("model_output_rich.json")).to_dict()
    event = wire["items"][0]
    assert (event["location"], event["notes"], event["duration_minutes"]) == (
        "Example Plaza office", "Bring the permit drawings", 90)
    assert (event["end_date"], event["end_time"]) == ("2026-11-12", "15:30")
    assert wire["items"][1]["notes"] == "Ask about the invoice" and "location" not in wire["items"][1]


def test_duration_crosses_midnight_and_an_explicit_end_wins():
    over = {"location": None, "notes": None, "attendees": []}
    late = model_item(kind="event", date="2026-11-12", time="23:30", duration_minutes=60, **over)
    stated = model_item(kind="event", date="2026-11-12", time="10:00", end_time="10:30", duration_minutes=120, **over)
    day = model_item(kind="event", date="2026-11-12", all_day=True, duration_minutes=60, **over)
    a, b, c = rich({"items": [late, stated, day]}).items
    assert (a.end_date, a.end_time) == ("2026-11-13", "00:30")
    assert (b.end_date, b.end_time, b.duration_minutes) == ("2026-11-12", "10:30", 30)  # recomputed from the end
    assert (c.end_date, c.end_time) == (None, None)


def test_default_wire_unchanged():
    wire = run(fixture("model_output.json")).to_dict()
    assert wire == fixture("expected_candidates.json")
    assert json.dumps(wire) == json.dumps(fixture("expected_candidates.json"))
    degraded = run(None, llm=None).to_dict()
    assert all("notes" not in i and "attendees" not in i for i in wire["items"] + degraded["items"])
    llm = FakeLlm(fixture("model_output.json"))
    run(None, llm=llm)
    assert "CAPTURE-PROMPT-V1" in llm.calls[0]["system"]
    # the same model answer with rich keys on it still gives the default wire when rich is off
    extra = {"items": [dict(model_item(), location="x", notes="y", duration_minutes=5, attendees=["z"])]}
    assert "notes" not in run(extra).to_dict()["items"][0]


def test_degraded_rich_answers_one_draft_with_null_rich_keys():
    wire = rich(None, llm=None, text="Call Sam tomorrow").to_dict()
    assert wire == fixture("expected_degraded_rich.json")
    bad = rich({"items": "nope"}).to_dict()
    assert bad["reason"] == "invalid_output" and bad["items"][0]["notes"] is None


def test_attendee_names_not_resolved():
    resolver = Resolver({("Dana", "contact"): [{"id": "c1", "label": "Dana Example"}]})
    item = model_item(kind="event", time="09:00", location=None, notes=None, duration_minutes=None,
                      attendees=["Dana", "dana", "  Lee  ", ""])
    result = rich({"items": [item]}, resolver=resolver)
    assert result.items[0].attendees == ("Dana", "Lee") and resolver.calls == []
    assert result.to_dict()["items"][0]["links"] == []


def test_rich_item_missing_a_rich_key_is_dropped_but_plain_parse_ignores_the_keys():
    assert rich({"items": [model_item()]}).degraded  # the only item is unusable
    assert not run({"items": [model_item()]}).degraded


def test_rich_text_is_cleaned_and_capped_and_impossible_durations_are_null():
    item = model_item(kind="event", time="09:00", location="Room\n4" + "x" * 300, notes="  ", duration_minutes=10**6,
                      attendees=[f"n{i}" for i in range(30)])
    event = rich({"items": [item]}).items[0]
    assert event.location.startswith("Room 4") and len(event.location) == 200
    assert event.notes is None and event.duration_minutes is None and len(event.attendees) == 10


def test_resolver_extra_keys_kept():
    rows = {("Sam", "contact"): [{"id": 7, "label": "Sam Example", "rank": 0.9, "kind": "x", "nested": {"a": 1}}]}
    item = model_item(links=[{"text": "Sam", "kind": "contact"}], location=None, notes=None,
                      duration_minutes=None, attendees=[])
    cand = rich({"items": [item]}, resolver=Resolver(rows)).items[0].links[0].candidates
    assert cand == ({"id": "7", "label": "Sam Example", "rank": 0.9, "kind": "x"},)
    plain = run({"items": [model_item(links=[{"text": "Sam", "kind": "contact"}])]}, resolver=Resolver(rows))
    assert plain.items[0].links[0].candidates == ({"id": "7", "label": "Sam Example"},)


def test_resolver_kinds():
    rows = {("Elm St", "place"): [{"id": "p1", "label": "Elm Street job"}]}
    resolver = Resolver(rows)
    links = [{"text": "Sam", "kind": "contact"}, {"text": "Elm St", "kind": "place"}, {"text": "Odd", "kind": "alien"}]
    llm = FakeLlm({"items": [model_item(links=links)]})
    result = run(None, llm=llm, resolver=resolver, resolver_kinds=("contact", "place"))
    assert resolver.calls == [("Sam", "contact"), ("Elm St", "place")]  # an unlisted kind is dropped, not resolved
    assert [l.kind for l in result.items[0].links] == ["contact", "place"]
    assert result.items[0].links[1].candidates == ({"id": "p1", "label": "Elm Street job"},)
    sent = llm.calls[0]
    assert sent["schema"]["properties"]["items"]["items"]["properties"]["links"]["items"]["properties"]["kind"][
        "enum"] == ["contact", "place"]
    assert '"contact", "place"' in sent["system"]


def test_resolver_kinds_default_leaves_prompt_and_schema_alone():
    assert build_prompt(TODAY, None, "UTC", EOD, kinds=("contact",)) == build_prompt(TODAY, None, "UTC", EOD)
    assert "Link kinds" in build_prompt(TODAY, None, "UTC", EOD, kinds=("contact", "place"))


@pytest.mark.parametrize("bad", [(), ("Contact",), ("a", "a"), ("x y",), ('a"b',), ("a" * 25,)])
def test_resolver_kinds_are_checked(bad):
    with pytest.raises(ValueError):
        run(None, llm=None, resolver_kinds=bad)
    with pytest.raises(TypeError):
        run(None, llm=None, resolver_kinds="contact")


def test_the_rich_prompt_is_filled_and_has_its_examples():
    prompt = build_prompt(TODAY, None, "America/Denver", EOD, rich=True)
    assert prompt.startswith("CAPTURE-PROMPT-V2") and "{{" not in prompt and "fifteen fields" in prompt
    assert "Site meeting with Dana and Lee" in prompt
    assert (FIXTURES / "rich_phrases.json").stat().st_size < 100_000
