import hashlib
from datetime import UTC, datetime

import pytest
from conftest import Notice, fixture

from bond_notify_py import (
    NOTICE_KEYS,
    InboxNotifier,
    dismiss,
    dismiss_for_source,
    list_notices,
    mark_all_read,
    mark_read,
    notice_cursor,
    notice_item,
    notice_routes,
    prune_notices,
)

NOW = datetime(2026, 11, 12, 15, 0, 0)


def row_from(item: dict) -> Notice:
    parse = datetime.fromisoformat
    return Notice(
        id=item["id"], user_id=item["user_id"], kind=item["kind"], title=item["title"], body=item["body"],
        data=dict(item["data"]), source_id=item["data"]["task_id"],
        created_at=parse(item["created_at"].removesuffix("Z")),
        read_at=parse(item["read_at"].removesuffix("Z")) if item["read_at"] else None,
        dismissed_at=parse(item["dismissed_at"].removesuffix("Z")) if item["dismissed_at"] else None,
    )


def test_notice_item_equals_the_fixture():
    expected = fixture("notice.json")
    assert tuple(expected) == NOTICE_KEYS
    assert notice_item(row_from(expected)) == expected


def test_notice_page_items_round_trip_and_the_count_matches():
    page = fixture("notices_page.json")
    assert [notice_item(row_from(i)) for i in page["items"]] == page["items"]
    assert page["unread_count"] == sum(1 for i in page["items"] if i["read_at"] is None)
    assert any(i["data"]["last"] for i in page["items"])


def test_notice_item_tolerates_sparse_data_and_does_not_mutate():
    row = Notice(id="a" * 32, user_id="u", kind="task_due", title="t", body="b", data={}, created_at=NOW)
    item = notice_item(row)
    assert item["data"]["actions"] == [] and item["data"]["last"] is False and item["data"]["due_at"] is None
    assert row.data == {}
    assert item["created_at"] == "2026-11-12T15:00:00Z" and item["read_at"] is None


def test_stubs_raise_not_implemented():
    calls = [
        lambda: InboxNotifier(Notice).write(None, []),
        lambda: list_notices(None, Notice, "u"),
        lambda: mark_read(None, Notice, "u", "id", NOW),
        lambda: mark_all_read(None, Notice, "u", NOW),
        lambda: dismiss(None, Notice, "u", "id", NOW),
        lambda: dismiss_for_source(None, Notice, "task", NOW),
        lambda: prune_notices(None, Notice, NOW),
        lambda: notice_routes(Notice),
    ]
    for call in calls:
        with pytest.raises(NotImplementedError):
            call()


def recomputed_id(item: dict) -> str:
    """sha256("task_id|user_id|stage|seq|token")[:32]; the token of a timed task is its due_at in epoch minutes."""
    data = item["data"]
    due = datetime.fromisoformat(data["due_at"].removesuffix("Z")).replace(tzinfo=UTC)
    token = str(int(due.timestamp() // 60))
    key = f"{data['task_id']}|{item['user_id']}|{data['stage']}|{data['seq']}|{token}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def test_fixture_ids_are_the_real_notice_ids():
    items = [fixture("notice.json"), *fixture("notices_page.json")["items"]]
    for item in items:
        assert item["id"] == recomputed_id(item), item["data"]["task_id"]


def test_notice_cursor_is_created_at_and_id():
    row = row_from(fixture("notice.json"))
    assert notice_cursor(row) == f"2026-11-12T14:30:05Z|{row.id}"


def test_notice_error_codes():
    from bond_notify_py import NoticeError

    assert NoticeError("notice_not_found").status == 404
    assert NoticeError("not_notice_owner").status == 403
