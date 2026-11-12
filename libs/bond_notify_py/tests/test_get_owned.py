"""get_owned: the public ownership check a host's own act route calls first."""
import pytest
from conftest import Notice
from test_inbox import N

from bond_notify_py import InboxNotifier, NoticeError, get_owned
from bond_notify_py import service as notify_service


def test_get_owned_returns_the_users_row(session):
    InboxNotifier(Notice).write(session, [N("a" * 32)])
    row = get_owned(session, Notice, "u1", "a" * 32)
    assert row.id == "a" * 32 and row.user_id == "u1"


def test_get_owned_refuses_another_users_notice_with_403(session):
    InboxNotifier(Notice).write(session, [N("a" * 32)])
    with pytest.raises(NoticeError) as err:
        get_owned(session, Notice, "u2", "a" * 32)
    assert (err.value.code, err.value.status) == ("not_notice_owner", 403)


def test_get_owned_missing_notice_is_404(session):
    with pytest.raises(NoticeError) as err:
        get_owned(session, Notice, "u1", "f" * 32)
    assert (err.value.code, err.value.status) == ("notice_not_found", 404)


def test_the_private_name_is_an_alias(session):
    assert notify_service._owned is get_owned
