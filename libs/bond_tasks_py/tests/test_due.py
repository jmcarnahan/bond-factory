"""Zone arithmetic and the one overdue definition (``due.py``)."""

from datetime import date, datetime, time, timedelta

import pytest
from conftest import Task

from bond_tasks_py import end_of_day_due, is_overdue, local_day_bounds, next_local_time, task_item, valid_zone

NY = "America/New_York"
LORD_HOWE = "Australia/Lord_Howe"  # 30-minute daylight saving shift
SYDNEY = "Australia/Sydney"  # southern hemisphere: daylight time starts in October


def hours(bounds: tuple[datetime, datetime]) -> float:
    return (bounds[1] - bounds[0]) / timedelta(hours=1)


def test_end_of_day_due_is_the_zone_conversion():
    assert end_of_day_due(date(2026, 3, 12), time(17, 0), "America/Los_Angeles") == datetime(2026, 3, 13, 0, 0)
    assert end_of_day_due(date(2026, 1, 12), time(17, 0), "UTC") == datetime(2026, 1, 12, 17, 0)


def test_a_time_that_does_not_exist_moves_forward():
    """2026-03-08 02:30 does not exist in New York; it becomes 03:30 daylight time (07:30 UTC)."""
    assert end_of_day_due(date(2026, 3, 8), time(2, 30), NY) == datetime(2026, 3, 8, 7, 30)


def test_an_ambiguous_time_takes_the_first_occurrence():
    """2026-11-01 01:30 happens twice in New York; the first is daylight time (05:30 UTC)."""
    assert end_of_day_due(date(2026, 11, 1), time(1, 30), NY) == datetime(2026, 11, 1, 5, 30)


def test_half_hour_shift_zone():
    assert end_of_day_due(date(2026, 10, 3), time(17, 0), LORD_HOWE) == datetime(2026, 10, 3, 6, 30)  # +10:30
    assert end_of_day_due(date(2026, 10, 5), time(17, 0), LORD_HOWE) == datetime(2026, 10, 5, 6, 0)  # +11:00
    start, end = local_day_bounds(date(2026, 10, 4), LORD_HOWE)
    assert (start, end) == (datetime(2026, 10, 3, 13, 30), datetime(2026, 10, 4, 13, 0))
    assert hours((start, end)) == 23.5


def test_day_bounds_on_change_days():
    assert hours(local_day_bounds(date(2026, 3, 8), NY)) == 23
    assert local_day_bounds(date(2026, 11, 1), NY) == (datetime(2026, 11, 1, 4, 0), datetime(2026, 11, 2, 5, 0))
    assert hours(local_day_bounds(date(2026, 11, 1), NY)) == 25
    assert hours(local_day_bounds(date(2026, 3, 9), NY)) == 24


def test_day_bounds_in_a_southern_zone():
    assert local_day_bounds(date(2026, 10, 4), SYDNEY) == (datetime(2026, 10, 3, 14, 0), datetime(2026, 10, 4, 13, 0))
    assert local_day_bounds(date(2026, 4, 5), SYDNEY) == (datetime(2026, 4, 4, 13, 0), datetime(2026, 4, 5, 14, 0))
    assert hours(local_day_bounds(date(2026, 4, 5), SYDNEY)) == 25  # daylight time ends


def test_next_local_time_is_strictly_after():
    la = "America/Los_Angeles"
    assert next_local_time(datetime(2026, 3, 12, 14, 59), time(8, 0), la) == datetime(2026, 3, 12, 15, 0)
    assert next_local_time(datetime(2026, 3, 12, 15, 0), time(8, 0), la) == datetime(2026, 3, 13, 15, 0)


def test_next_local_time_across_a_gap_and_a_half_hour_zone():
    assert next_local_time(datetime(2026, 3, 8, 6, 59), time(2, 30), NY) == datetime(2026, 3, 8, 7, 30)
    assert next_local_time(datetime(2026, 3, 8, 7, 30), time(2, 30), NY) == datetime(2026, 3, 9, 6, 30)
    assert next_local_time(datetime(2026, 10, 3, 20, 0), time(8, 0), LORD_HOWE) == datetime(2026, 10, 3, 21, 0)


def test_valid_zone():
    assert valid_zone("UTC") and valid_zone("America/Los_Angeles") and valid_zone(LORD_HOWE)
    for bad in ("Mars/Base", "", "../etc/passwd", "x" * 70, None, 5):
        assert valid_zone(bad) is False


def task(**kw) -> Task:
    base = {"owner_user_id": "u1", "created_by": "u1", "title": "t", "status": "open"}
    return Task(**{**base, **kw})


NOW = datetime(2026, 3, 11, 20, 0)


def test_overdue_by_the_instant():
    t = task(due_date=date(2026, 3, 11), due_time="09:00", due_at=datetime(2026, 3, 11, 16, 0))
    assert is_overdue(t, NOW) is True
    assert is_overdue(t, datetime(2026, 3, 11, 16, 0)) is False  # exactly at the instant is not past it
    assert is_overdue(t, datetime(2026, 3, 11, 15, 59)) is False
    # the instant wins over the viewer's date
    assert is_overdue(t, NOW, viewer_today=date(2026, 3, 11)) is True
    assert is_overdue(task(due_date=date(2026, 3, 9), due_at=datetime(2026, 3, 12, 0, 0)), NOW,
                      viewer_today=date(2026, 3, 11)) is False


def test_overdue_needs_an_open_task():
    for status in ("done", "cancelled"):
        assert is_overdue(task(status=status, due_at=datetime(2026, 3, 1)), NOW) is False


def test_overdue_falls_back_to_the_date_only_with_a_viewer_today():
    t = task(due_date=date(2026, 3, 10))
    assert is_overdue(t, NOW, viewer_today=date(2026, 3, 11)) is True
    assert is_overdue(t, NOW, viewer_today=date(2026, 3, 10)) is False
    assert is_overdue(t, NOW) is False


def test_an_undated_task_is_never_overdue():
    assert is_overdue(task(), NOW, viewer_today=date(2030, 1, 1)) is False


def test_serialize_uses_the_one_definition():
    t = task(due_date=date(2026, 3, 11), due_time="09:00", due_at=datetime(2026, 3, 11, 16, 0))
    assert task_item(t, today=date(2026, 3, 11), now=NOW)["overdue"] is is_overdue(t, NOW) is True
    assert task_item(t, today=date(2026, 3, 11), now=datetime(2026, 3, 11, 16, 0))["overdue"] is False  # at the instant


def test_overdue_accepts_aware_values():
    from datetime import UTC

    t = task(due_at=datetime(2026, 3, 11, 16, 0))
    assert is_overdue(t, datetime(2026, 3, 11, 17, 0, tzinfo=UTC)) is True


@pytest.mark.parametrize("zone", [NY, LORD_HOWE, SYDNEY, "Europe/London", "Asia/Kolkata"])
def test_day_bounds_tile_the_calendar(zone):
    """Each day ends where the next begins, in every zone, across the year."""
    day = date(2026, 1, 1)
    for _ in range(366):
        start, end = local_day_bounds(day, zone)
        assert end == local_day_bounds(day + timedelta(days=1), zone)[0] and end > start
        day += timedelta(days=1)
