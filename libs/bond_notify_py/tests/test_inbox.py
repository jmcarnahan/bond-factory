"""Notifier, services and sync routes against in-memory SQLite."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from conftest import Notice, fixture
from sqlalchemy import func, select

from bond_notify_py import (
    InboxNotifier,
    NoticeError,
    dismiss,
    dismiss_for_source,
    dismiss_stale,
    list_notices,
    mark_all_read,
    mark_read,
    notice_item,
    notice_routes,
    prune_notices,
    verdict_for,
)

NOW = datetime(2026, 11, 12, 15, 0, 0)
T0 = datetime(2026, 11, 12, 14, 30, 5)


@dataclass
class N:
    notice_id: str
    task_id: str = "task-1"
    user_id: str = "u1"
    stage: str = "due"
    seq: int = 0
    kind: str = "task_due"
    title: str = "Due now: x"
    body: str = "This task is due now."
    due_at: datetime | None = datetime(2026, 11, 12, 14, 30)
    priority: int | None = 2
    route: str | None = "/tasks/task-1"
    created_at: datetime = T0
    actions: tuple = ("done", "snooze", "cancel")
    last: bool = False


def count(session) -> int:
    return session.execute(select(func.count()).select_from(Notice)).scalar_one()


def test_write_inside_a_rolled_back_savepoint_leaves_nothing(session):
    outer = session.begin_nested()
    InboxNotifier(Notice).write(session, [N("a" * 32)])
    assert count(session) == 1
    outer.rollback()
    assert count(session) == 0


def test_same_notice_twice_is_one_row_and_keeps_its_state(session):
    notifier = InboxNotifier(Notice)
    notifier.write(session, [N("a" * 32)])
    mark_read(session, Notice, "u1", "a" * 32, NOW)
    notifier.write(session, [N("a" * 32, title="changed")])
    assert count(session) == 1
    row = session.get(Notice, "a" * 32)
    assert row.read_at == NOW and row.title == "Due now: x"


def test_batch_with_one_present_inserts_only_the_new_one(session):
    notifier = InboxNotifier(Notice)
    notifier.write(session, [N("a" * 32)])
    notifier.write(session, [N("a" * 32), N("b" * 32)])
    assert sorted(r.id for r in session.execute(select(Notice)).scalars()) == ["a" * 32, "b" * 32]


def test_empty_batch_is_a_no_op_and_title_is_truncated(session):
    notifier = InboxNotifier(Notice)
    notifier.write(session, [])
    assert count(session) == 0
    notifier.write(session, [N("a" * 32, title="t" * 300)])
    assert len(session.get(Notice, "a" * 32).title) == 255


def test_notifier_row_equals_the_fixture_wire_shape(session):
    expected = fixture("notice.json")
    d = expected["data"]
    notice = N(expected["id"], task_id=d["task_id"], user_id=expected["user_id"], stage=d["stage"], seq=d["seq"],
               title=expected["title"], body=expected["body"], route=d["route"], priority=d["priority"],
               due_at=datetime(2026, 11, 12, 14, 30), created_at=datetime(2026, 11, 12, 14, 30, 5),
               actions=tuple(d["actions"]), last=d["last"])
    InboxNotifier(Notice).write(session, [notice])
    row = session.get(Notice, expected["id"])
    assert row.source_id == "task-0001"
    assert notice_item(row) == expected


def seed(session, n, user="u1", at=T0, source="t", start=0):
    InboxNotifier(Notice).write(session, [N(f"{i:032x}", user_id=user, created_at=at, task_id=source)
                                          for i in range(start, start + n)])


def test_paging_120_notices_with_one_created_at_returns_each_once(session):
    seed(session, 120)
    seen, cursor = [], None
    while True:
        rows, unread, cursor = list_notices(session, Notice, "u1", limit=25, before=cursor)
        seen += [r.id for r in rows]
        assert unread == 120
        if cursor is None:
            break
    assert len(seen) == 120 == len(set(seen))
    assert seen == sorted(seen, reverse=True)


def test_paging_with_microsecond_stamps_loses_nothing(session):
    InboxNotifier(Notice).write(session, [
        N(f"{i:032x}", created_at=datetime(2026, 11, 12, 14, 30, 5, 100 * i)) for i in range(1, 8)])
    seen, cursor = [], None
    while True:
        rows, _, cursor = list_notices(session, Notice, "u1", limit=3, before=cursor)
        seen += [r.id for r in rows]
        if cursor is None:
            break
    assert len(seen) == 7 == len(set(seen))


def test_order_is_newest_first_and_bad_cursor_is_refused(session):
    InboxNotifier(Notice).write(session, [N("a" * 32, created_at=T0), N("b" * 32, created_at=T0 + timedelta(1))])
    rows, _, nxt = list_notices(session, Notice, "u1")
    assert [r.id for r in rows] == ["b" * 32, "a" * 32] and nxt is None
    with pytest.raises(NoticeError) as err:
        list_notices(session, Notice, "u1", before="garbage")
    assert err.value.code == "invalid_cursor"


def test_unread_filter_dismissed_hidden_and_count_ignores_the_page(session):
    seed(session, 5)
    mark_read(session, Notice, "u1", f"{4:032x}", NOW)
    dismiss(session, Notice, "u1", f"{3:032x}", NOW)
    rows, unread, _ = list_notices(session, Notice, "u1")
    assert len(rows) == 4 and unread == 3
    rows, unread, _ = list_notices(session, Notice, "u1", unread=True, limit=1)
    assert len(rows) == 1 and unread == 3 and all(r.read_at is None for r in rows)
    assert list_notices(session, Notice, "other") == ([], 0, None)


def test_read_is_idempotent_and_keeps_the_first_stamp(session):
    seed(session, 1)
    mark_read(session, Notice, "u1", f"{0:032x}", NOW)
    row = mark_read(session, Notice, "u1", f"{0:032x}", NOW + timedelta(hours=1))
    assert row.read_at == NOW


def test_dismiss_also_reads_and_keeps_first_stamps(session):
    seed(session, 1)
    row = dismiss(session, Notice, "u1", f"{0:032x}", NOW)
    assert row.dismissed_at == NOW and row.read_at == NOW
    row = dismiss(session, Notice, "u1", f"{0:032x}", NOW + timedelta(hours=1))
    assert row.dismissed_at == NOW


def test_read_all_counts_only_changed_rows_of_the_user(session):
    seed(session, 4)
    seed(session, 2, user="u2", start=100)
    mark_read(session, Notice, "u1", f"{0:032x}", NOW)
    assert mark_all_read(session, Notice, "u1", NOW) == 3
    assert mark_all_read(session, Notice, "u1", NOW) == 0
    assert list_notices(session, Notice, "u2")[1] == 2


def test_ownership_and_missing_errors(session):
    seed(session, 1)
    for call in (mark_read, dismiss):
        with pytest.raises(NoticeError) as err:
            call(session, Notice, "u2", f"{0:032x}", NOW)
        assert (err.value.code, err.value.status) == ("not_notice_owner", 403)
        with pytest.raises(NoticeError) as err:
            call(session, Notice, "u1", "missing", NOW)
        assert (err.value.code, err.value.status) == ("notice_not_found", 404)
    assert session.get(Notice, f"{0:032x}").read_at is None


def test_dismiss_for_source_covers_every_user_and_only_that_task(session):
    InboxNotifier(Notice).write(session, [
        N("a" * 32, user_id="u1"), N("b" * 32, user_id="u2"), N("c" * 32, user_id="u1", task_id="other")])
    mark_read(session, Notice, "u1", "a" * 32, T0)
    assert dismiss_for_source(session, Notice, "task-1", NOW) == 2
    a, b, c = (session.get(Notice, x * 32) for x in "abc")
    assert a.dismissed_at == NOW and b.dismissed_at == NOW and c.dismissed_at is None
    assert a.read_at == T0 and b.read_at == NOW
    assert dismiss_for_source(session, Notice, "task-1", NOW) == 0


def test_dismiss_for_source_can_be_limited_to_chosen_users(session):
    InboxNotifier(Notice).write(session, [N("a" * 32, user_id="u1"), N("b" * 32, user_id="u2")])
    assert dismiss_for_source(session, Notice, "task-1", NOW, user_ids=[]) == 0
    assert dismiss_for_source(session, Notice, "task-1", NOW, user_ids={"u1"}) == 1
    assert stored(session, "a" * 32).dismissed_at == NOW
    assert stored(session, "b" * 32).dismissed_at is None
    assert dismiss_for_source(session, Notice, "task-1", NOW, user_ids=None) == 1


def test_prune_removes_old_read_dismissed_and_very_old_only(session):
    old = NOW - timedelta(days=31)
    InboxNotifier(Notice).write(session, [
        N("a" * 32, created_at=NOW), N("b" * 32, created_at=NOW), N("c" * 32, created_at=NOW),
        N("d" * 32, created_at=NOW - timedelta(days=91)), N("e" * 32, created_at=NOW),
        N("f" * 32, created_at=NOW)])
    mark_read(session, Notice, "u1", "a" * 32, old)  # read long ago
    dismiss(session, Notice, "u1", "b" * 32, old)  # dismissed long ago
    mark_read(session, Notice, "u1", "c" * 32, NOW - timedelta(days=5))  # read recently
    dismiss(session, Notice, "u1", "e" * 32, NOW - timedelta(days=5))
    assert prune_notices(session, Notice, NOW) == 3
    assert sorted(r.id[0] for r in session.execute(select(Notice)).scalars()) == ["c", "e", "f"]


OLD_DUE = datetime(2026, 11, 12, 14, 30)
NEW_DUE = datetime(2026, 11, 19, 14, 30)


def test_new_due_instant_puts_away_the_old_notices_of_that_user_and_task(session):
    notifier = InboxNotifier(Notice)
    notifier.write(session, [N("a" * 32, stage="past", seq=1), N("b" * 32, user_id="u2")])
    notifier.write(session, [N("c" * 32, due_at=NEW_DUE, created_at=NOW)])
    a, b, c = (session.get(Notice, x * 32) for x in "abc")
    assert a.dismissed_at == NOW and a.read_at == NOW  # stale, same user and task
    assert b.dismissed_at is None  # another user: not in this batch
    assert c.dismissed_at is None and c.read_at is None
    assert [r.id for r in list_notices(session, Notice, "u1")[0]] == ["c" * 32]


def test_same_due_instant_keeps_earlier_notices_live(session):
    notifier = InboxNotifier(Notice)
    notifier.write(session, [N("a" * 32, stage="close", due_at=OLD_DUE)])
    notifier.write(session, [N("b" * 32, stage="due", due_at=OLD_DUE)])
    assert session.get(Notice, "a" * 32).dismissed_at is None


def test_dismiss_stale_keeps_matching_due_and_dismisses_every_user(session):
    InboxNotifier(Notice).write(session, [
        N("a" * 32, user_id="u1"), N("b" * 32, user_id="u2"),
        N("c" * 32, user_id="u1", task_id="other")])
    assert dismiss_stale(session, Notice, "task-1", "2026-11-12T14:30:00Z", NOW) == 0
    assert dismiss_stale(session, Notice, "task-1", NEW_DUE, NOW) == 2
    a, b, c = (session.get(Notice, x * 32) for x in "abc")
    assert a.dismissed_at == NOW and b.dismissed_at == NOW and c.dismissed_at is None
    assert dismiss_stale(session, Notice, "task-1", NEW_DUE, NOW) == 0


def test_dismiss_stale_with_none_dismisses_all_of_the_task(session):
    InboxNotifier(Notice).write(session, [N("a" * 32), N("b" * 32, due_at=None)])
    assert dismiss_stale(session, Notice, "task-1", None, NOW) == 2


PLUS5 = timezone(timedelta(hours=5))
AWARE_NOW = datetime(2026, 11, 12, 20, 0, 0, tzinfo=PLUS5)  # the same instant as NOW


def stored(session, notice_id):
    session.expire_all()
    return session.get(Notice, notice_id)


def test_aware_now_is_stored_as_naive_utc_everywhere(session):
    seed(session, 4)
    ids = [f"{i:032x}" for i in range(4)]
    mark_read(session, Notice, "u1", ids[0], AWARE_NOW)
    assert stored(session, ids[0]).read_at == NOW
    dismiss(session, Notice, "u1", ids[1], AWARE_NOW)
    row = stored(session, ids[1])
    assert row.dismissed_at == NOW and row.read_at == NOW
    assert mark_all_read(session, Notice, "u1", AWARE_NOW) == 2
    assert stored(session, ids[2]).read_at == NOW
    seed(session, 1, source="s2", start=10)
    assert dismiss_for_source(session, Notice, "s2", AWARE_NOW) == 1
    assert stored(session, f"{10:032x}").dismissed_at == NOW
    assert dismiss_stale(session, Notice, "t", None, AWARE_NOW) == 3
    assert stored(session, ids[3]).dismissed_at == NOW


def test_aware_now_in_prune_uses_the_utc_instant(session):
    seed(session, 1)
    mark_read(session, Notice, "u1", f"{0:032x}", NOW - timedelta(days=30, minutes=1))
    assert prune_notices(session, Notice, AWARE_NOW) == 1


def test_aware_created_at_is_stored_as_naive_utc(session):
    InboxNotifier(Notice).write(session, [N("a" * 32, created_at=AWARE_NOW)])
    assert stored(session, "a" * 32).created_at == NOW


def test_sync_patch_stores_naive_utc_for_an_aware_clock(session):
    seed(session, 1)
    handler = notice_routes(Notice, now=lambda: AWARE_NOW)[("notices", None)].handler
    handler(session, ctx("u1"), op(f"{0:032x}"), {"dismissed_at": "x"})
    row = stored(session, f"{0:032x}")
    assert row.dismissed_at == NOW and row.read_at == NOW


def test_offset_cursor_is_converted_and_returns_the_right_page(session):
    seed(session, 3)
    ids = [f"{i:032x}" for i in range(3)]
    for stamp in ("2026-11-12T19:30:05+05:00", "2026-11-12T14:30:05Z", "2026-11-12T14:30:05"):
        rows, _, _ = list_notices(session, Notice, "u1", before=f"{stamp}|{ids[2]}")
        assert [r.id for r in rows] == [ids[1], ids[0]], stamp


@pytest.mark.parametrize("cursor", [
    "garbage", "|", "2026-11-12T14:30:05Z|", "|abc", "2026-11-12T14:30:05Z", "nope|abc",
    "2026-11-12T14:30:05Z|has space", "2026-11-12T14:30:05Z|a;b", "2026-11-12T14:30:05Z|" + "a" * 65,
    "2026-11-12T14:30:05Z|a|b"])
def test_malformed_cursors_are_refused(session, cursor):
    with pytest.raises(NoticeError) as err:
        list_notices(session, Notice, "u1", before=cursor)
    assert err.value.code == "invalid_cursor"


def ctx(user):
    return SimpleNamespace(user=user)


def op(row_id, kind="patch"):
    return SimpleNamespace(op=kind, id=row_id)


def test_sync_routes_shape():
    route = notice_routes(Notice)[("notices", None)]
    assert route.ops == frozenset({"patch"}) and route.reads == ("read_at", "dismissed_at")
    assert list(notice_routes(Notice)) == [("notices", None)]


def test_sync_patch_on_own_row_stamps_server_time(session):
    seed(session, 2)
    handler = notice_routes(Notice, now=lambda: NOW)[("notices", None)].handler
    handler(session, ctx("u1"), op(f"{0:032x}"), {"read_at": "1999-01-01T00:00:00Z"})
    row = session.get(Notice, f"{0:032x}")
    assert row.read_at == NOW and row.dismissed_at is None
    handler(session, ctx(SimpleNamespace(user_id="u1")), op(f"{1:032x}"), {"dismissed_at": "x", "title": "no"})
    row = session.get(Notice, f"{1:032x}")
    assert row.dismissed_at == NOW and row.read_at == NOW and row.title == "Due now: x"


def test_sync_null_clears_nothing_and_first_stamp_stays(session):
    seed(session, 1)
    later = [NOW]
    handler = notice_routes(Notice, now=lambda: later[0])[("notices", None)].handler
    handler(session, ctx("u1"), op(f"{0:032x}"), {"read_at": "x"})
    later[0] = NOW + timedelta(hours=1)
    handler(session, ctx("u1"), op(f"{0:032x}"), {"read_at": None, "dismissed_at": None})
    row = session.get(Notice, f"{0:032x}")
    assert row.read_at == NOW and row.dismissed_at is None


def test_sync_patch_refuses_another_users_row_and_unknown_row(session):
    seed(session, 1)
    handler = notice_routes(Notice, now=lambda: NOW)[("notices", None)].handler
    with pytest.raises(NoticeError) as err:
        handler(session, ctx("u2"), op(f"{0:032x}"), {"read_at": "x"})
    assert verdict_for(err.value) == ("forbidden", "not_notice_owner")
    assert session.get(Notice, f"{0:032x}").read_at is None
    with pytest.raises(NoticeError) as err:
        handler(session, ctx("u1"), op("nope"), {"read_at": "x"})
    assert verdict_for(err.value) == ("not_found", "notice_not_found")
    assert verdict_for(ValueError("x")) is None
