"""Rich mode: a type slip in an optional rich field costs the field, never the item."""

import math

import pytest
from conftest import FakeLlm, event_item, model_item, run
from test_rich import Resolver, rich

REQUIRED = {"location": None, "notes": None, "duration_minutes": None, "attendees": []}


def ev(**over):
    return event_item(**{**REQUIRED, "time": "10:00", "all_day": False, **over})


def one(**over):
    result = rich({"items": [ev(**over)]})
    assert not result.degraded and len(result.items) == 1, result
    return result.items[0]


@pytest.mark.parametrize("field,bad", [("attendees", None), ("attendees", "Ann"), ("attendees", {"a": 1}),
                                       ("location", []), ("location", 5), ("notes", 5), ("notes", {"x": 1}),
                                       ("duration_minutes", []), ("duration_minutes", True)])
def test_a_slip_in_an_optional_field_keeps_the_item(field, bad):
    item = one(**{field: bad})
    assert item.title == "Lunch"
    assert getattr(item, field) in (None, ())


@pytest.mark.parametrize("value,expected", [(30, 30), ("30", 30), (" 45 ", 45), (30.0, 30), ("30.0", 30),
                                            (30.5, None), ("30.5", None), ("abc", None), (0, None), (-5, None),
                                            ("-5", None), (math.nan, None), (math.inf, None), ("1e999", None),
                                            (10081, None)])
def test_duration_is_a_whole_positive_number_or_null(value, expected):
    assert one(duration_minutes=value).duration_minutes == expected


def test_a_missing_rich_key_still_fails_the_item():
    bad = ev()
    del bad["notes"]
    assert rich({"items": [bad, model_item(title="ok", **REQUIRED)]}).dropped == 1


def test_attendees_with_addresses_or_links_are_dropped():
    item = one(attendees=["Ann Lee", "ann@example.com", "https://x.test/a", "ftp://h", "Bo", 7, None, "ann lee"])
    assert item.attendees == ("Ann Lee", "Bo")


def test_a_stated_end_recomputes_the_wire_duration():
    both = one(end_time="11:15", duration_minutes=30)
    assert (both.end_time, both.duration_minutes) == ("11:15", 75)
    wire = rich({"items": [ev(end_time="11:15", duration_minutes=30)]}).to_dict()["items"][0]
    assert wire["duration_minutes"] == 75
    over_midnight = one(time="23:00", end_date="2026-11-13", end_time="01:00", duration_minutes=5)
    assert over_midnight.duration_minutes == 120
    assert one(end_time="10:00", duration_minutes=30).duration_minutes is None  # a zero length is null
    # an end that is not usable never leaves a stale length behind
    all_day = rich({"items": [event_item(**{**REQUIRED, "end_date": "2026-11-14", "duration_minutes": 60})]}).items[0]
    assert all_day.end_date == "2026-11-14" and all_day.duration_minutes is None
    assert one(end_time="12:00", duration_minutes=None).duration_minutes == 120


def test_no_end_keeps_the_stated_duration_and_derives_the_end():
    item = one(duration_minutes=90)
    assert (item.end_date, item.end_time, item.duration_minutes) == ("2026-11-12", "11:30", 90)


def test_non_finite_resolver_values_are_dropped_from_the_row():
    rows = {("Sam", "contact"): [{"id": "1", "label": "Sam", "rank": math.nan, "far": math.inf, "ok": 0.5, "n": 3}]}
    item = model_item(links=[{"text": "Sam", "kind": "contact"}], **REQUIRED)
    (cand,) = rich({"items": [item]}, resolver=Resolver(rows)).items[0].links[0].candidates
    assert cand == {"id": "1", "label": "Sam", "ok": 0.5, "n": 3}


def test_an_unlisted_link_kind_is_dropped_not_resolved():
    resolver = Resolver()
    links = [{"text": "Sam", "kind": "alien"}, {"text": "Elm", "kind": "place"}, {"text": "Ann", "kind": 5}]
    result = rich({"items": [ev(links=links)]}, resolver=resolver, resolver_kinds=("place", "contact"))
    assert resolver.calls == [("Elm", "place")]
    assert [(l.text, l.kind) for l in result.items[0].links] == [("Elm", "place")]
    plain = run({"items": [model_item(links=[{"text": "Sam", "kind": "alien"}])]}, resolver=Resolver())
    # one kind (the default): whatever the model calls it, it is that kind, as before
    assert [(l.text, l.kind) for l in plain.items[0].links] == [("Sam", "contact")]


def test_prompt_names_the_listed_kinds_in_rule_and_examples():
    for is_rich in (False, True):
        llm = FakeLlm({"items": []})
        run({"items": []}, llm=llm, rich=is_rich, resolver_kinds=("place", "company"))
        system = llm.calls[0]["system"]
        assert '"kind":"contact"' not in system and '"kind": "contact"' not in system
        assert '"kind": one of "place", "company"' in system and '"kind":"place"' in system
        assert 'Link kinds: a link\'s kind is one of "place", "company"' in system
    llm = FakeLlm({"items": []})
    run({"items": []}, llm=llm, resolver_kinds=("company", "contact"))
    assert '"kind":"contact"' in llm.calls[0]["system"]  # the examples keep contact when it is listed
    default = FakeLlm({"items": []})
    run({"items": []}, llm=default)
    assert '"kind": "contact"' in default.calls[0]["system"] and "Link kinds" not in default.calls[0]["system"]


def test_a_flood_of_attendees_is_bounded_and_deduplicated():
    names = [f"Name{i % 3}" for i in range(50_000)] + ["Late"]
    item = one(attendees=names)
    assert item.attendees == ("Name0", "Name1", "Name2")  # only a bounded head of the list is looked at


def test_an_all_day_event_has_no_duration():
    result = rich({"items": [event_item(**{**REQUIRED, "time": None, "all_day": True, "duration_minutes": 90})]})
    (item,) = result.items
    assert item.all_day and item.duration_minutes is None and item.end_time is None
