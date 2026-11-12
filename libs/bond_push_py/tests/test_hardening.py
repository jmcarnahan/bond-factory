"""Input safety, naive UTC, iOS-only sending, and the register race."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest
from conftest import Base, PushDevice
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import bond_push_py.devices as devices_module
from bond_push_py import (
    MockSender,
    PushError,
    PushNotifier,
    PushResult,
    device_routes,
    devices_for,
    register_device,
    to_naive_utc,
)

NOW = datetime(2026, 11, 12, 15, 0, 0)
PLUS5 = timezone(timedelta(hours=5))
NOW_PLUS5 = datetime(2026, 11, 12, 20, 0, 0, tzinfo=PLUS5)  # the same instant as NOW


def reg(session, user="u1", device="d1", token="tok1", platform="ios", **kw):
    args = {"user_id": user, "device_id": device, "token": token, "platform": platform,
            "environment": "sandbox", "topic": "com.example.app", "now": NOW}
    args.update(kw)
    return register_device(session, PushDevice, **args)


def rows(session):
    return session.execute(select(PushDevice)).scalars().all()


# 1. non-string input is a coded refusal -------------------------------------------------------------------

BAD = [123, 5.5, True, [], ["x"], {}, {"a": 1}, None, b"bytes"]


@pytest.mark.parametrize("bad", BAD)
@pytest.mark.parametrize(
    ("field", "code"),
    [("token", "token_required"), ("device_id", "device_id_required"), ("platform", "invalid_platform"),
     ("environment", "invalid_environment")],
)
def test_register_device_refuses_non_strings(session, bad, field, code):
    kwargs = {"token": "t", "device_id": "d", "platform": "ios", "environment": "sandbox"}
    kwargs[field] = bad
    with pytest.raises(PushError) as err:
        register_device(session, PushDevice, user_id="u1", topic=None, now=NOW, **kwargs)
    assert err.value.code == code
    assert rows(session) == []


@pytest.mark.parametrize("bad", [7, 1.5, True, ["x"], {"a": 1}, b"b"])
def test_register_device_refuses_a_non_string_topic(session, bad):
    with pytest.raises(PushError) as err:
        reg(session, topic=bad)
    assert err.value.code == "invalid_topic"


@dataclass
class Ctx:
    user: str


@dataclass
class Op:
    op: str
    id: str


def route_run(session, op, row_id, data, user="u1"):
    route = device_routes(PushDevice, now=lambda: NOW)[("push_devices", None)]
    route.handler(session, Ctx(user), Op(op, row_id), data)


def good():
    return {"token": "tok1", "platform": "ios", "environment": "sandbox", "topic": "com.example.app",
            "device_id": "d1"}


@pytest.mark.parametrize("bad", BAD)
@pytest.mark.parametrize(
    "field", ["token", "device_id", "platform", "environment", "topic"],
)
def test_put_with_a_non_string_field_is_a_push_error_never_a_type_error(session, bad, field):
    data = good() | {field: bad}
    try:
        route_run(session, "put", "row-1", data)
    except PushError as err:
        assert rows(session) == [] and err.code
    else:  # None and empty containers for the optional topic mean "no topic"
        assert field == "topic" and bad in (None, [], {})


@pytest.mark.parametrize("bad", BAD)
@pytest.mark.parametrize("field", ["token", "platform", "environment", "topic"])
def test_patch_with_a_non_string_field_is_a_push_error_never_a_type_error(session, bad, field):
    route_run(session, "put", "row-1", good())
    try:
        route_run(session, "patch", "row-1", {field: bad})
    except PushError:
        pass
    else:
        assert field == "topic" and bad in (None, [], {})
    (row,) = rows(session)
    assert row.token == "tok1" and row.platform == "ios" and row.environment == "sandbox"


# 2. naive UTC ---------------------------------------------------------------------------------------------

def test_to_naive_utc():
    assert to_naive_utc(NOW_PLUS5) == NOW and to_naive_utc(NOW_PLUS5).tzinfo is None
    assert to_naive_utc(NOW) is NOW


def test_register_device_stores_an_aware_now_as_naive_utc(session):
    row = reg(session, now=NOW_PLUS5)
    session.refresh(row)
    assert row.last_seen_at == NOW and row.created_at == NOW
    assert row.last_seen_at.tzinfo is None


def test_sync_handlers_store_naive_utc_for_an_aware_clock(session):
    route = device_routes(PushDevice, now=lambda: NOW_PLUS5)[("push_devices", None)]
    route.handler(session, Ctx("u1"), Op("put", "row-1"), good())
    route.handler(session, Ctx("u1"), Op("patch", "row-1"), {"token": "tok2"})
    (row,) = rows(session)
    assert row.last_seen_at == NOW and row.created_at == NOW


@dataclass
class Notice:
    notice_id: str = "n" * 32
    task_id: str = "task-1"
    user_id: str = "u1"
    title: str = "T"
    body: str = "B"
    route: str | None = None
    created_at: datetime = NOW


def test_notifier_normalises_aware_times(session):
    dead = reg(session)
    sender = MockSender(fail=PushResult(ok=False, unregistered=True, error="Unregistered"))
    notifier = PushNotifier(PushDevice, sender, now=lambda: NOW_PLUS5)
    notifier.send(session, Notice(created_at=NOW_PLUS5 - timedelta(seconds=100)))
    assert sender.sent[0].expires_at == NOW + timedelta(seconds=500)
    assert dead.disabled_at == NOW and dead.disabled_at.tzinfo is None


# 3. iOS only ----------------------------------------------------------------------------------------------

def test_devices_for_defaults_to_ios_and_can_be_widened(session):
    reg(session, device="a", token="ta", platform="ios")
    reg(session, device="b", token="tb", platform="web")
    reg(session, device="c", token="tc", platform="android")
    assert [r.device_id for r in devices_for(session, PushDevice, "u1")] == ["a"]
    assert {r.device_id for r in devices_for(session, PushDevice, "u1", None)} == {"a", "b", "c"}
    assert [r.device_id for r in devices_for(session, PushDevice, "u1", "web")] == ["b"]


def test_a_user_with_only_web_or_android_rows_is_ok_and_those_rows_stay_live(session):
    web = reg(session, device="b", token="tb", platform="web")
    android = reg(session, device="c", token="tc", platform="android")
    sender = MockSender()
    assert PushNotifier(PushDevice, sender, now=lambda: NOW).send(session, Notice()) == "ok"
    assert sender.sent == []
    assert web.disabled_at is None and android.disabled_at is None


def test_only_the_ios_rows_receive_a_push(session):
    reg(session, device="a", token="ta", platform="ios")
    reg(session, device="b", token="tb", platform="web")
    sender = MockSender()
    PushNotifier(PushDevice, sender, now=lambda: NOW).send(session, Notice())
    assert [m.token for m in sender.sent] == ["ta"]


# 4. the register race -------------------------------------------------------------------------------------

@pytest.fixture
def two_sessions(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'race.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as a, Session(engine) as b:
        yield a, b
    engine.dispose()


def inject_after_first_release(monkeypatch, other_session, **competitor):
    """Run a competing register, committed, right after the first ``release_token`` of the call under test."""
    real = devices_module.release_token
    state = {"done": False}

    def wrapper(*args, **kw):
        real(*args, **kw)
        if not state["done"]:
            state["done"] = True
            register_device(other_session, PushDevice, now=NOW, platform="ios", environment="sandbox",
                            topic=None, **competitor)
            other_session.commit()

    monkeypatch.setattr(devices_module, "release_token", wrapper)


def test_a_concurrent_register_of_the_same_device_updates_instead_of_failing(two_sessions, monkeypatch):
    a, b = two_sessions
    inject_after_first_release(monkeypatch, b, user_id="u1", device_id="d1", token="theirs")
    row = reg(a, token="mine")
    a.commit()
    (found,) = rows(a)
    assert found is row and found.token == "mine" and found.device_id == "d1"


def test_a_concurrent_register_of_the_same_token_moves_it_instead_of_failing(two_sessions, monkeypatch):
    a, b = two_sessions
    inject_after_first_release(monkeypatch, b, user_id="u2", device_id="d9", token="mine")
    reg(a, token="mine")
    a.commit()
    assert [(r.user_id, r.token) for r in rows(a)] == [("u1", "mine")]


def test_a_persistent_collision_is_a_coded_conflict_not_an_integrity_error(session):
    reg(session, user="u2", device="other", token="x", row_id="taken-id")
    with pytest.raises(PushError) as err:
        reg(session, user="u1", device="d1", token="y", row_id="taken-id")
    assert err.value.code == "device_conflict" and err.value.status == 409
    assert [r.user_id for r in rows(session)] == ["u2"]  # the session is still usable and unchanged
