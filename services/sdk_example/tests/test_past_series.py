"""The past-due series: one notice shortly after the due time, then one each morning, then it stops."""

import pytest
from connections_util import headers
from todo_util import inbox, notices_of, sweep, timed

MORNINGS = ["2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13", "2026-11-14"]


@pytest.fixture
def h(client):
    return headers(client)


def test_the_series_ends_after_max_past_with_the_last_notice_flagged(client, app, h):
    task = timed(client, h)  # due 2026-11-09 10:00 UTC; work day 08:00 to 17:00
    sweep(client, h, "2026-11-09T10:20:00Z")
    for day in MORNINGS:
        sweep(client, h, f"{day}T08:30:00Z")
    rows = notices_of(app, task["id"])
    assert [n.data["seq"] for n in rows] == [0, 1, 2, 3, 4, 5]
    assert [n.data["last"] for n in rows] == [False] * 5 + [True]
    assert {n.data["stage"] for n in rows} == {"past"}
    assert "last reminder" in rows[-1].body
    for day in ("2026-11-15", "2026-11-16", "2026-11-17"):
        assert sweep(client, h, f"{day}T08:30:00Z")["sweep"]["claimed"] == 0
    assert len(notices_of(app, task["id"])) == 6
    assert len([n for n in inbox(client, h) if n["data"]["task_id"] == task["id"]]) == 6


def test_a_day_with_no_sweep_makes_seq_jump_without_a_flood(client, app, h):
    task = timed(client, h)
    sweep(client, h, "2026-11-09T10:20:00Z")
    sweep(client, h, "2026-11-12T08:30:00Z")  # three days later: one notice, not three
    assert [n.data["seq"] for n in notices_of(app, task["id"])] == [0, 3]


def test_a_task_moved_to_a_new_time_puts_the_old_notices_away(client, app, h):
    task = timed(client, h)
    sweep(client, h, "2026-11-09T10:20:00Z")
    client.put(f"/tasks/{task['id']}", json={"due_time": "15:00", "time_zone": "UTC"}, headers=h)
    assert inbox(client, h) == []  # made for the old due instant
    sweep(client, h, "2026-11-09T15:05:00Z")
    fresh = inbox(client, h)
    assert [n["data"]["stage"] for n in fresh] == ["due"] and fresh[0]["data"]["due_at"] == "2026-11-09T15:00:00Z"
