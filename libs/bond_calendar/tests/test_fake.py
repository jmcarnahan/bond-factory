import ast
from datetime import UTC, datetime
from pathlib import Path

import pytest

import bond_calendar
from bond_calendar import (
    CalendarEventDraft,
    CalendarProvider,
    EtagMismatch,
    FakeCalendarProvider,
    NotFound,
    ReconnectRequired,
    Unavailable,
)

T0 = datetime(2026, 7, 2, 10, tzinfo=UTC)
T1 = datetime(2026, 7, 2, 11, tzinfo=UTC)
DAY = (datetime(2026, 7, 1, tzinfo=UTC), datetime(2026, 7, 31, tzinfo=UTC))


def draft(subject="A", start=T0, end=T1, **kw):
    return CalendarEventDraft(subject, start, end, **kw)


def test_fake_satisfies_the_protocol():
    assert isinstance(FakeCalendarProvider(), CalendarProvider)


def test_create_assigns_id_and_first_etag():
    fake = FakeCalendarProvider()
    event = fake.create_event(draft(attendees=["a@example.com"]))
    assert event.id == "fake-1" and event.etag == 'W/"1"' and event.is_organizer
    assert fake.events[0].subject == "A" and fake.events[0].attendees[0].email == "a@example.com"


def test_etag_increments_on_every_update():
    fake = FakeCalendarProvider()
    e = fake.create_event(draft())
    e2 = fake.update_event(e.id, {"subject": "B"})
    e3 = fake.update_event(e.id, {"location": "Here"}, etag=e2.etag)
    assert (e2.etag, e3.etag) == ('W/"2"', 'W/"3"') and e3.subject == "B" and e3.location == "Here"


def test_stale_etag_raises_and_changes_nothing():
    fake = FakeCalendarProvider()
    e = fake.create_event(draft())
    fake.update_event(e.id, {"subject": "B"})
    with pytest.raises(EtagMismatch):
        fake.update_event(e.id, {"subject": "C"}, etag=e.etag)
    assert fake.events[0].subject == "B" and fake.events[0].etag == 'W/"2"'


def test_update_converts_times_and_body():
    fake = FakeCalendarProvider()
    e = fake.create_event(draft())
    out = fake.update_event(e.id, {"start": datetime(2026, 7, 2, 12), "is_all_day": False, "body": "notes",
                                   "body_type": "html"})
    assert out.start == datetime(2026, 7, 2, 12, tzinfo=UTC) and out.preview == "notes"
    assert fake.get_event(e.id, include_body=True).body == "notes" and fake.get_event(e.id).body is None


@pytest.mark.parametrize("patch", [{"start": T0}, {"end": T1}])
def test_time_patch_without_is_all_day_is_a_value_error(patch):
    fake = FakeCalendarProvider()
    e = fake.create_event(draft())
    with pytest.raises(ValueError):
        fake.update_event(e.id, patch)
    assert fake.events[0].etag == 'W/"1"'


def test_id_prefix_makes_ids_unique_per_instance():
    first, second = FakeCalendarProvider(id_prefix="fake-a"), FakeCalendarProvider(id_prefix="fake-b")
    assert first.create_event(draft()).id == "fake-a-1" and second.create_event(draft()).id == "fake-b-1"
    assert FakeCalendarProvider().create_event(draft()).id == "fake-1"


def test_update_and_get_missing_raise_not_found():
    fake = FakeCalendarProvider()
    with pytest.raises(NotFound):
        fake.update_event("nope", {"subject": "x"})
    with pytest.raises(NotFound):
        fake.get_event("nope")


def test_delete_is_idempotent():
    fake = FakeCalendarProvider()
    e = fake.create_event(draft())
    fake.delete_event(e.id)
    fake.delete_event(e.id)
    assert fake.events == []


def test_list_filters_by_window_orders_and_truncates():
    fake = FakeCalendarProvider()
    fake.create_event(draft("late", datetime(2026, 7, 5, 9, tzinfo=UTC), datetime(2026, 7, 5, 10, tzinfo=UTC)))
    fake.create_event(draft("early"))
    fake.create_event(draft("outside", datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 9, 1, 1, tzinfo=UTC)))
    page = fake.list_events(start=DAY[0], end=DAY[1])
    assert [e.subject for e in page.events] == ["early", "late"] and not page.truncated
    short = fake.list_events(start=DAY[0], end=DAY[1], max_events=1)
    assert len(short.events) == 1 and short.truncated


def test_list_hides_cancelled_unless_asked():
    fake = FakeCalendarProvider()
    e = fake.create_event(draft())
    fake.update_event(e.id, {"subject": "x"})
    fake.events[0].is_cancelled = True
    assert fake.list_events(start=DAY[0], end=DAY[1]).events == []
    assert len(fake.list_events(start=DAY[0], end=DAY[1], include_cancelled=True).events) == 1


@pytest.mark.parametrize("exc", [ReconnectRequired(), Unavailable()])
def test_fail_next_raises_once_then_recovers(exc):
    fake = FakeCalendarProvider()
    fake.fail_next(exc)
    with pytest.raises(type(exc)):
        fake.create_event(draft())
    assert fake.events == []
    fake.create_event(draft())
    assert len(fake.events) == 1


def test_calls_are_recorded():
    fake = FakeCalendarProvider()
    e = fake.create_event(draft())
    fake.delete_event(e.id)
    assert [name for name, _ in fake.calls] == ["create_event", "delete_event"]


def test_returned_events_are_copies():
    fake = FakeCalendarProvider()
    e = fake.create_event(draft())
    e.subject = "changed outside"
    assert fake.events[0].subject == "A"


def test_lib_imports_only_httpx_and_the_standard_library():
    allowed = {"httpx", "bond_calendar"}
    root = Path(bond_calendar.__file__).parent
    found: set[str] = set()
    for path in root.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                found |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                found.add(node.module.split(".")[0])
    third_party = {m for m in found if m not in allowed and m not in __import__("sys").stdlib_module_names}
    assert third_party == set()
