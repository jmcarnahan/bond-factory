"""Every rule that checks the model's answer locally, whatever the vendor promised."""

import pytest
from conftest import FakeLlm, event_item, model_item, run

from bond_capture_py import MAX_ITEMS, MAX_LINKS


def ok(*items):
    result = run({"items": list(items)})
    assert not result.degraded, result.reason
    return result.items


def invalid(*items, answer=None):
    result = run(answer if answer is not None else {"items": list(items)})
    assert result.degraded and result.reason == "invalid_output"


def test_an_empty_answer_is_a_valid_nothing():
    result = run({"items": []})
    assert result.items == () and not result.degraded and result.reason is None


def test_extra_items_are_dropped():
    items = ok(*[model_item(title=f"t{i}") for i in range(MAX_ITEMS + 4)])
    assert [i.title for i in items] == [f"t{i}" for i in range(MAX_ITEMS)]


@pytest.mark.parametrize("value", ["2026-13-45", "2026-02-30", "2026-1-5", "20261112", "tomorrow", 20261112, ""])
def test_a_bad_date_invalidates_the_answer(value):
    invalid(model_item(date=value))
    invalid(event_item(date=value))
    invalid(model_item(end_date=value))


@pytest.mark.parametrize("value", ["25:00", "9:00", "12:60", "noon", 900, "12:00:00"])
def test_a_bad_time_invalidates_the_answer(value):
    invalid(model_item(time=value))
    invalid(model_item(end_time=value))


@pytest.mark.parametrize("value", [0, 4, -1, "2", 2.5, 3.0000001, True, [2]])
def test_a_bad_priority_drops_the_item(value):
    invalid(model_item(priority=value))
    kept = ok(model_item(priority=value), model_item(title="kept"))
    assert [i.title for i in kept] == ["kept"]


def test_a_whole_number_float_priority_is_accepted_as_an_integer():
    items = ok(model_item(priority=2.0), model_item(priority=3.0))
    assert [i.priority for i in items] == [2, 3] and all(type(i.priority) is int for i in items)


def test_priority_one_to_three_or_null_is_kept():
    assert [i.priority for i in ok(*[model_item(priority=p) for p in (1, 2, 3, None)])] == [1, 2, 3, None]


def test_shape_and_kind_failures_invalidate_the_answer():
    invalid(model_item(kind="reminder"))
    invalid(model_item(kind=None))
    invalid(model_item(title=7))
    invalid(model_item(due_defaulted="no"))
    invalid(model_item(all_day=1))
    invalid(model_item(links="Sam"))
    invalid(model_item(links=["Sam"]))
    invalid("not an item")
    missing = model_item()
    del missing["confidence"]
    invalid(missing)
    invalid(answer={"items": "nope"})
    invalid(answer={"nothing": []})
    invalid(answer=["items"])


def test_confidence_is_clamped_and_low_confidence_is_flagged_below_half():
    items = ok(model_item(confidence=1.7), model_item(confidence=-3), model_item(confidence=0.49),
               model_item(confidence=0.5))
    assert [i.confidence for i in items] == [1.0, 0.0, 0.49, 0.5]
    assert [i.flags for i in items] == [(), ("low_confidence",), ("low_confidence",), ()]
    invalid(model_item(confidence="high"))
    invalid(model_item(confidence=True))
    invalid(model_item(confidence=float("nan")))


def test_titles_are_stripped_capped_at_255_and_an_empty_title_drops_the_item():
    items = ok(model_item(title="  Call Sam  "), model_item(title="   "), model_item(title=""),
               model_item(title="x" * 300), model_item(title="kept"))
    assert [i.title for i in items] == ["Call Sam", "x" * 255, "kept"]


def test_a_task_dated_before_today_becomes_today_and_a_future_one_is_kept():
    past, future = ok(model_item(date="2026-11-01", time="09:00"), model_item(date="2026-12-01", time="09:00"))
    # a passed date is a default, and its clock time goes: "yesterday 09:00" must not be overdue when saved
    assert (past.due_date, past.due_time, past.due_defaulted) == ("2026-11-11", None, True)
    assert (future.due_date, future.due_time, future.due_defaulted) == ("2026-12-01", "09:00", False)


def test_dates_beyond_five_years_drop_the_item_and_keep_the_others():
    items = ok(model_item(title="far", date="2031-11-12"), event_item(title="far event", date="2040-01-01"),
               model_item(title="edge", date="2031-11-11"), model_item(title="far end", end_date="2099-01-01"),
               model_item(title="near"))
    assert [i.title for i in items] == ["edge", "near"]


def test_an_event_with_no_date_becomes_a_task_due_today_defaulted():
    (item,) = ok(event_item(date=None, time="15:00", priority=3, title="Dentist"))
    assert (item.kind, item.title, item.due_date, item.due_time, item.due_defaulted) == (
        "task", "Dentist", "2026-11-11", "15:00", True)
    assert item.priority == 3


def test_a_task_with_no_date_gets_today_defaulted_and_keeps_its_time():
    (item,) = ok(model_item(date=None, time="16:30"))
    assert (item.due_date, item.due_time, item.due_defaulted) == ("2026-11-11", "16:30", True)


def test_task_mapping_uses_due_fields_and_drops_event_only_fields():
    (item,) = ok(model_item(time="12:00", priority=3, all_day=True, end_date="2026-11-20", end_time="13:00"))
    wire = item.to_dict()
    assert wire["kind"] == "task" and wire["due_time"] == "12:00" and "end_date" not in wire


def test_events_with_a_date_and_no_time_are_all_day_whatever_the_model_said():
    plain, timed = ok(event_item(all_day=False), event_item(all_day=True, time="14:00", end_time="15:00"))
    assert (plain.all_day, plain.start_time) == (True, None)
    assert (timed.all_day, timed.start_time, timed.end_time) == (False, "14:00", "15:00")


def test_an_all_day_event_has_no_end_time_and_an_end_before_the_start_is_dropped():
    span, backwards = ok(event_item(end_date="2026-11-13", end_time="17:00"), event_item(end_date="2026-11-01"))
    assert (span.end_date, span.end_time) == ("2026-11-13", None)
    assert backwards.end_date is None


def test_an_event_in_the_past_is_missed_never_overdue():
    yesterday, today, tomorrow, task = ok(event_item(date="2026-11-10"), event_item(date="2026-11-11"),
                                          event_item(date="2026-11-12"), model_item(date="2026-11-10"))
    assert yesterday.flags == ("missed",) and yesterday.start_date == "2026-11-10"
    assert today.flags == () and tomorrow.flags == () and task.flags == ()
    assert "overdue" not in str([i.flags for i in (yesterday, today, tomorrow, task)])
    (both,) = ok(event_item(date="2026-11-10", confidence=0.2))
    assert both.flags == ("low_confidence", "missed")


def test_links_are_capped_trimmed_and_forced_to_contact():
    links = [{"text": f"Name{i}", "kind": "contact"} for i in range(MAX_LINKS + 3)]
    (item,) = ok(model_item(links=links))
    assert [link.text for link in item.links] == [f"Name{i}" for i in range(MAX_LINKS)]
    (item,) = ok(model_item(links=[{"text": "  Acme  ", "kind": "organization"}, {"text": " ", "kind": "contact"},
                                   {"text": "y" * 200, "kind": "deal"}]))
    assert [(link.text, link.kind) for link in item.links] == [("Acme", "contact"), ("y" * 80, "contact")]


def test_a_resolver_is_not_asked_about_dropped_items_or_blank_links():
    class Spy:
        def __init__(self):
            self.names = []

        def resolve(self, user_id, name, kind):
            self.names.append(name)
            return []

    spy = Spy()
    answer = {"items": [model_item(title="", links=[{"text": "Dropped", "kind": "contact"}]),
                        model_item(links=[{"text": "Kept", "kind": "contact"}])]}
    run(None, llm=FakeLlm(answer), resolver=spy)
    assert spy.names == ["Kept"]
