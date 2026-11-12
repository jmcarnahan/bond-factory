"""The same writes on PostgreSQL, where the unique token and (user, device) constraints are enforced for real.

Run with BOND_TEST_POSTGRES_URL set (``make pg-up`` then ``make test-pg`` at the repo root); skipped otherwise.
"""

from datetime import datetime

import pytest
from conftest import PushDevice
from sqlalchemy import select
from sqlalchemy.orm import Session

import bond_push_py.devices as devices_module
from bond_push_py import PushError, device_routes, devices_for, register_device, unregister_device

pytestmark = pytest.mark.postgres

NOW = datetime(2026, 11, 12, 15, 0, 0)


def reg(session, user="u1", device="d1", token="tok1", **kw):
    args = {"user_id": user, "device_id": device, "token": token, "platform": "ios",
            "environment": "sandbox", "topic": "com.example.app", "now": NOW}
    args.update(kw)
    return register_device(session, PushDevice, **args)


def rows(session):
    return session.execute(select(PushDevice)).scalars().all()


def test_register_is_idempotent(pg_session):
    first = reg(pg_session)
    second = reg(pg_session, token="tok2", environment="production")
    pg_session.commit()
    (row,) = rows(pg_session)
    assert second.id == first.id == row.id
    assert (row.token, row.environment) == ("tok2", "production")


def test_token_moves_between_users_without_a_unique_violation(pg_session):
    reg(pg_session, user="u1", device="d1", token="shared")
    reg(pg_session, user="u2", device="d9", token="shared")
    pg_session.commit()
    assert [(r.user_id, r.token) for r in rows(pg_session)] == [("u2", "shared")]


def test_token_swap_between_a_users_devices(pg_session):
    reg(pg_session, device="d1", token="t1")
    reg(pg_session, device="d2", token="t2")
    reg(pg_session, device="d2", token="t1")
    pg_session.commit()
    assert [(r.device_id, r.token) for r in rows(pg_session)] == [("d2", "t1")]


def test_unregister_and_devices_for(pg_session):
    reg(pg_session)
    reg(pg_session, device="d2", token="t2").disabled_at = NOW
    pg_session.commit()
    assert [r.device_id for r in devices_for(pg_session, PushDevice, "u1")] == ["d1"]
    assert unregister_device(pg_session, PushDevice, user_id="u1", device_id="d1") is True
    assert unregister_device(pg_session, PushDevice, user_id="u1", device_id="d1") is False


def test_over_length_input_is_a_coded_refusal_not_a_database_error(pg_session):
    with pytest.raises(PushError) as err:
        reg(pg_session, token="x" * 256)
    assert err.value.code == "token_too_long"
    with pytest.raises(PushError) as err:
        reg(pg_session, device="d" * 65)
    assert err.value.code == "device_id_too_long"


class Ctx:
    def __init__(self, user):
        self.user = user


class Op:
    def __init__(self, op, id):
        self.op, self.id = op, id


def run(session, user, op, row_id, data):
    route = device_routes(PushDevice, now=lambda: NOW)[("push_devices", None)]
    route.handler(session, Ctx(user), Op(op, row_id), data)
    session.flush()


def body(device="d1", token="tok1"):
    return {"token": token, "platform": "ios", "environment": "sandbox", "topic": "com.example.app",
            "device_id": device}


def test_route_collisions_are_coded_refusals(pg_session):
    run(pg_session, "u1", "put", "d_" + "a" * 32, body())
    with pytest.raises(PushError) as err:  # another user's row id
        run(pg_session, "u2", "put", "d_" + "a" * 32, body(token="other"))
    assert err.value.code == "not_device_owner"
    run(pg_session, "u2", "put", "d_" + "b" * 32, body(device="phone"))  # takes u1's token: it moves
    assert [(r.user_id, r.token) for r in rows(pg_session)] == [("u2", "tok1")]
    run(pg_session, "u2", "put", "d_" + "c" * 32, body(device="phone", token="tok2"))  # same device, new id
    (row,) = rows(pg_session)
    assert row.id == "d_" + "b" * 32 and row.token == "tok2"


def test_route_patch_moves_a_held_token_and_changes_environment(pg_session):
    run(pg_session, "u1", "put", "d_" + "a" * 32, body())
    run(pg_session, "u2", "put", "d_" + "b" * 32, body(device="d2", token="tok2"))
    run(pg_session, "u2", "patch", "d_" + "b" * 32, {"token": "tok1", "environment": "production"})
    (row,) = rows(pg_session)
    assert (row.user_id, row.token, row.environment) == ("u2", "tok1", "production")


def _inject_after_first_release(monkeypatch, other, **competitor):
    """Run a competing register, committed, right after the first ``release_token`` of the call under test."""
    real = devices_module.release_token
    state = {"done": False}

    def wrapper(*args, **kw):
        real(*args, **kw)
        if not state["done"]:
            state["done"] = True
            register_device(other, PushDevice, now=NOW, platform="ios", environment="sandbox", topic=None,
                            **competitor)
            other.commit()

    monkeypatch.setattr(devices_module, "release_token", wrapper)


def test_two_sessions_racing_on_one_device_do_not_raise(pg_session, monkeypatch):
    with Session(pg_session.get_bind()) as other:
        _inject_after_first_release(monkeypatch, other, user_id="u1", device_id="d1", token="theirs")
        row = reg(pg_session, token="mine")
        pg_session.commit()
        (found,) = rows(pg_session)
        assert found is row and found.token == "mine"


def test_two_sessions_racing_on_one_token_move_it(pg_session, monkeypatch):
    with Session(pg_session.get_bind()) as other:
        _inject_after_first_release(monkeypatch, other, user_id="u2", device_id="d9", token="mine")
        reg(pg_session, token="mine")
        pg_session.commit()
        assert [(r.user_id, r.token) for r in rows(pg_session)] == [("u1", "mine")]
