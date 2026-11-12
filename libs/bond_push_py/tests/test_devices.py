import hashlib
from datetime import datetime, timedelta

import pytest
from conftest import PushDevice, fixture
from sqlalchemy import select

from bond_push_py import PushError, device_row_id, devices_for, register_device, unregister_device

NOW = datetime(2026, 11, 12, 15, 0, 0)


def reg(session, user="u1", device="d1", token="tok1", now=NOW, **kw):
    args = {"user_id": user, "device_id": device, "token": token, "platform": "ios",
            "environment": "sandbox", "topic": "com.example.app", "now": now}
    args.update(kw)
    return register_device(session, PushDevice, **args)


def rows(session):
    return session.execute(select(PushDevice)).scalars().all()


def test_register_from_the_shared_fixture(session):
    item = fixture("device_register.json")
    row = register_device(session, PushDevice, user_id="u1", now=NOW, **item)
    assert (row.token, row.platform, row.environment, row.topic) == (
        item["token"], "ios", "sandbox", "com.example.app")
    assert row.device_id == item["device_id"] and row.last_seen_at == NOW and row.created_at == NOW
    assert row.id and row.disabled_at is None


def test_register_is_idempotent_per_user_and_device(session):
    first = reg(session)
    later = NOW + timedelta(days=1)
    second = reg(session, token="tok2", platform="web", environment="production", topic="other", now=later)
    assert second is first and len(rows(session)) == 1
    assert (first.token, first.platform, first.environment, first.topic) == ("tok2", "web", "production", "other")
    assert first.last_seen_at == later and first.created_at == NOW


def test_register_clears_disabled_at(session):
    row = reg(session)
    row.disabled_at = NOW
    reg(session, now=NOW + timedelta(hours=1))
    assert row.disabled_at is None


def test_token_moves_between_users_in_one_flush(session):
    reg(session, user="u1", device="d1", token="shared")
    mine = reg(session, user="u2", device="d9", token="shared")
    found = rows(session)
    assert [(r.user_id, r.device_id, r.token) for r in found] == [("u2", "d9", "shared")]
    assert found[0] is mine


def test_token_moves_between_devices_of_one_user(session):
    reg(session, device="d1", token="t1")
    reg(session, device="d2", token="t2")
    reg(session, device="d2", token="t1")  # d2 takes d1's token
    assert [(r.device_id, r.token) for r in rows(session)] == [("d2", "t1")]


def test_device_row_id_formula_is_pinned():
    expected = "d_" + hashlib.sha256(b"u1|device-0001").hexdigest()[:32]
    assert device_row_id("u1", "device-0001") == expected
    assert expected == "d_dc3d1e5ab21c3dc51c4d543ffbbb9f7c"  # a literal the phone's test can share
    assert device_row_id("u2", "device-0001") != expected


def test_new_rows_get_the_formula_id_when_no_row_id_is_given(session):
    row = reg(session, user="u1", device="device-0001")
    assert row.id == device_row_id("u1", "device-0001")
    assert reg(session, user="u1", device="device-0001", token="tok2").id == row.id


def test_row_id_is_used_for_a_new_row_only(session):
    row = reg(session, row_id="fixed-id")
    assert row.id == "fixed-id"
    assert reg(session, row_id="other-id").id == "fixed-id"


@pytest.mark.parametrize(
    ("override", "code"),
    [
        ({"platform": "windows"}, "invalid_platform"),
        ({"environment": "staging"}, "invalid_environment"),
        ({"token": ""}, "token_required"),
        ({"token": "   "}, "token_required"),
        ({"device_id": ""}, "device_id_required"),
        ({"token": "x" * 256}, "token_too_long"),
        ({"device_id": "d" * 65}, "device_id_too_long"),
        ({"topic": "t" * 256}, "topic_too_long"),
    ],
)
def test_validation_errors_are_coded_and_write_nothing(session, override, code):
    with pytest.raises(PushError) as err:
        reg(session, **override)
    assert err.value.code == code and err.value.status == 422
    assert rows(session) == []


def test_all_three_platforms_and_both_environments_are_accepted(session):
    for i, platform in enumerate(("ios", "android", "web")):
        reg(session, device=f"d{i}", token=f"t{i}", platform=platform)
    reg(session, device="dp", token="tp", environment="production")
    assert len(rows(session)) == 4


def test_unregister(session):
    reg(session)
    reg(session, user="u2", token="tok2")
    assert unregister_device(session, PushDevice, user_id="u1", device_id="d1") is True
    assert unregister_device(session, PushDevice, user_id="u1", device_id="d1") is False
    assert [r.user_id for r in rows(session)] == ["u2"]


def test_devices_for_hides_disabled_and_orders_newest_first(session):
    reg(session, device="old", token="a", now=NOW)
    reg(session, device="new", token="b", now=NOW + timedelta(hours=2))
    dead = reg(session, device="dead", token="c", now=NOW + timedelta(hours=3))
    dead.disabled_at = NOW
    reg(session, user="u2", device="x", token="d")
    assert [r.device_id for r in devices_for(session, PushDevice, "u1")] == ["new", "old"]
    assert devices_for(session, PushDevice, "nobody") == []
