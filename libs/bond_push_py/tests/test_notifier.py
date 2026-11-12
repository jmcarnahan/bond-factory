from dataclasses import dataclass
from datetime import datetime, timedelta

from conftest import PushDevice

from bond_push_py import MockSender, NullSender, PushNotifier, PushResult, register_device

NOW = datetime(2026, 11, 12, 15, 0, 0)


@dataclass
class Notice:
    notice_id: str = "n" * 32
    task_id: str = "task-1"
    user_id: str = "u1"
    title: str = "Pay rent"
    body: str = "Due now"
    route: str | None = "/tasks/task-1"
    created_at: datetime = NOW


def add(session, device, token, **kw):
    return register_device(session, PushDevice, user_id=kw.pop("user", "u1"), device_id=device, token=token,
                           platform="ios", environment=kw.pop("environment", "sandbox"), topic="com.example.app",
                           now=NOW)


def notifier(sender, **kw):
    return PushNotifier(PushDevice, sender, now=lambda: NOW, **kw)


def test_message_fields(session):
    add(session, "d1", "t1", environment="production")
    sender = MockSender()
    assert notifier(sender).send(session, Notice()) == "ok"
    (m,) = sender.sent
    assert (m.token, m.environment, m.topic) == ("t1", "production", "com.example.app")
    assert (m.title, m.body) == ("Pay rent", "Due now")
    assert m.collapse_id == "n" * 32 and m.thread_id == "task-1"
    assert m.data == {"notice_id": "n" * 32, "task_id": "task-1", "route": "/tasks/task-1"}
    assert m.expires_at == NOW + timedelta(seconds=600)
    assert m.category is None


def test_category_only_when_the_constructor_gets_one(session):
    add(session, "d1", "t1")
    sender = MockSender()
    notifier(sender, category="bond.task").send(session, Notice())
    assert sender.sent[0].category == "bond.task"


def test_expiry_counts_from_the_notice_and_never_lies_in_the_past(session):
    add(session, "d1", "t1")
    sender = MockSender()
    notifier(sender, expires_in=300).send(session, Notice(created_at=NOW - timedelta(seconds=100)))
    notifier(sender, expires_in=300).send(session, Notice(created_at=NOW - timedelta(hours=3)))
    assert [m.expires_at for m in sender.sent] == [NOW + timedelta(seconds=200), NOW + timedelta(seconds=300)]


def test_only_the_recipients_live_devices_get_a_message(session):
    add(session, "d1", "t1")
    add(session, "d2", "t2").disabled_at = NOW
    add(session, "d3", "t3", user="u2")
    sender = MockSender()
    assert notifier(sender).send(session, Notice()) == "ok"
    assert [m.token for m in sender.sent] == ["t1"]


def test_one_unregistered_device_is_disabled_and_the_other_makes_it_ok(session):
    good = add(session, "d1", "good")
    bad = add(session, "d2", "bad")
    sender = MockSender(fail_tokens={"bad": PushResult(ok=False, unregistered=True, error="BadDeviceToken")})
    assert notifier(sender).send(session, Notice()) == "ok"
    assert bad.disabled_at == NOW and good.disabled_at is None


def test_all_unregistered(session):
    a, b = add(session, "d1", "a"), add(session, "d2", "b")
    sender = MockSender(fail=PushResult(ok=False, unregistered=True, error="Unregistered"))
    assert notifier(sender).send(session, Notice()) == "unregistered"
    assert a.disabled_at == NOW and b.disabled_at == NOW
    assert notifier(sender).send(session, Notice()) == "ok"  # none live now


def test_retryable_when_none_accepted(session):
    add(session, "d1", "a")
    add(session, "d2", "b")
    sender = MockSender(fail_tokens={"a": PushResult(ok=False, retryable=True, error="503"),
                                     "b": PushResult(ok=False, unregistered=True, error="Unregistered")})
    row_b = next(r for r in session.query(PushDevice) if r.token == "b")
    assert notifier(sender).send(session, Notice()) == "retryable"
    assert row_b.disabled_at == NOW


def test_one_accepted_and_one_retryable_is_retryable(session):
    add(session, "d1", "good")
    add(session, "d2", "later")
    sender = MockSender(fail_tokens={"later": PushResult(ok=False, retryable=True, error="503")})
    assert notifier(sender).send(session, Notice()) == "retryable"


def test_accepted_plus_unregistered_or_failed_is_ok(session):
    add(session, "d1", "good")
    add(session, "d2", "dead")
    add(session, "d3", "broken")
    sender = MockSender(fail_tokens={"dead": PushResult(ok=False, unregistered=True, error="Unregistered"),
                                     "broken": PushResult(ok=False, error="PayloadEmpty")})
    assert notifier(sender).send(session, Notice()) == "ok"


def test_failed_is_permanent(session):
    add(session, "d1", "a")
    assert notifier(NullSender()).send(session, Notice()) == "failed"
    sender = MockSender(fail=PushResult(ok=False, error="PayloadEmpty"))
    assert notifier(sender).send(session, Notice()) == "failed"


def test_no_live_device_is_ok_and_sends_nothing(session):
    sender = MockSender()
    assert notifier(sender).send(session, Notice()) == "ok"
    assert sender.sent == []
