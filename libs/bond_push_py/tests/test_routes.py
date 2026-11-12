from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest
from conftest import PushDevice
from sqlalchemy import select

from bond_push_py import PushError, device_routes, device_row_id, register_device, verdict_for

NOW = datetime(2026, 11, 12, 15, 0, 0)
LATER = NOW + timedelta(hours=1)


@dataclass
class Ctx:
    user: object


@dataclass
class Op:
    op: str
    id: str


@dataclass
class UserObj:
    user_id: str


def insert(user="u1", device="d1", token="tok1"):
    return {"token": token, "platform": "ios", "environment": "sandbox", "topic": "com.example.app",
            "device_id": device, "user_id": "attacker"}


@pytest.fixture
def route():
    return device_routes(PushDevice, now=lambda: LATER)[("push_devices", None)]


ALIAS: dict[str, str] = {}


@pytest.fixture(autouse=True)
def _clear_aliases():
    ALIAS.clear()


def real(alias):
    return ALIAS.get(alias, alias)


def run(route, session, user, op, row_id, data=None):
    """``row-N`` aliases stand for the formula id of the first put's (user, device); other ids pass through."""
    data = data or {}
    if row_id.startswith("row-") and row_id not in ALIAS and op == "put" and isinstance(data.get("device_id"), str):
        uid = user if isinstance(user, str) else user.user_id
        ALIAS[row_id] = device_row_id(uid, data["device_id"])
    route.handler(session, Ctx(user), Op(op, real(row_id)), data)


def all_rows(session):
    return session.execute(select(PushDevice)).scalars().all()


def test_route_shape(route):
    assert set(device_routes(PushDevice)) == {("push_devices", None)}
    assert route.ops == frozenset({"put", "patch", "delete"})
    assert set(route.reads) == {"token", "platform", "environment", "topic", "device_id"}


def test_put_creates_own_row_with_op_id_and_ignores_client_user_id(route, session):
    run(route, session, "u1", "put", "row-1", insert())
    (row,) = all_rows(session)
    assert (row.id, row.user_id, row.device_id, row.token) == (real("row-1"), "u1", "d1", "tok1")
    assert row.last_seen_at == LATER


def test_ctx_user_may_be_an_object(route, session):
    run(route, session, UserObj("u9"), "put", "row-1", insert())
    assert all_rows(session)[0].user_id == "u9"


def test_put_replay_updates_the_same_row(route, session):
    run(route, session, "u1", "put", "row-1", insert())
    run(route, session, "u1", "put", "row-1", insert(token="tok2") | {"device_id": "changed"})
    (row,) = all_rows(session)
    assert (row.id, row.device_id, row.token) == (real("row-1"), "d1", "tok2")


def test_put_onto_another_users_row_id_is_refused(route, session):
    run(route, session, "u1", "put", "row-1", insert())
    with pytest.raises(PushError) as err:
        run(route, session, "u2", "put", "row-1", insert(token="other"))
    assert err.value.code == "not_device_owner"
    assert [(r.user_id, r.token) for r in all_rows(session)] == [("u1", "tok1")]


def test_put_with_a_token_held_elsewhere_moves_it(route, session):
    run(route, session, "u1", "put", "row-1", insert())
    run(route, session, "u2", "put", "row-2", insert(device="phone"))
    assert [(r.id, r.user_id) for r in all_rows(session)] == [(real("row-2"), "u2")]


def test_put_validation_is_a_coded_refusal(route, session):
    bad = insert() | {"platform": "toaster"}
    with pytest.raises(PushError) as err:
        run(route, session, "u1", "put", "row-1", bad)
    assert verdict_for(err.value) == ("invalid", "invalid_platform")
    with pytest.raises(PushError) as err:
        run(route, session, "u1", "put", "row-1", {})
    assert err.value.code == "device_id_required"


def test_patch_updates_the_writable_fields_but_never_the_device_id(route, session):
    run(route, session, "u1", "put", "row-1", insert())
    row = all_rows(session)[0]
    row.disabled_at = NOW
    run(route, session, "u1", "patch", "row-1",
        {"token": "tok2", "topic": "com.example.other", "device_id": "zzz", "user_id": "x"})
    assert (row.token, row.platform, row.topic) == ("tok2", "ios", "com.example.other")
    assert (row.device_id, row.user_id, row.environment) == ("d1", "u1", "sandbox")
    assert row.last_seen_at == LATER and row.disabled_at is None


def test_patch_sandbox_to_production_with_a_new_token_in_one_write(route, session):
    run(route, session, "u1", "put", "row-1", insert())
    run(route, session, "u1", "patch", "row-1", {"token": "prod-tok", "environment": "production"})
    (row,) = all_rows(session)
    assert (row.token, row.environment, row.platform, row.topic) == ("prod-tok", "production", "ios",
                                                                   "com.example.app")


def test_patch_validates_like_register_and_writes_nothing_on_refusal(route, session):
    run(route, session, "u1", "put", "row-1", insert())
    for bad, code in (({"environment": "staging"}, "invalid_environment"), ({"platform": "toaster"}, "invalid_platform"),
                      ({"platform": ""}, "invalid_platform"), ({"topic": "t" * 256}, "topic_too_long"),
                      ({"token": "x" * 256}, "token_too_long")):
        with pytest.raises(PushError) as err:
            run(route, session, "u1", "patch", "row-1", {"token": "changed"} | bad)
        assert err.value.code == code
    row = all_rows(session)[0]
    assert (row.token, row.environment, row.platform, row.last_seen_at) == ("tok1", "sandbox", "ios", LATER)


def test_android_and_web_are_refused_on_put_and_patch(route, session):
    for platform in ("android", "web"):
        with pytest.raises(PushError) as err:
            run(route, session, "u1", "put", "row-1", insert() | {"platform": platform})
        assert err.value.code == "invalid_platform"
    run(route, session, "u1", "put", "row-1", insert())
    with pytest.raises(PushError) as err:
        run(route, session, "u1", "patch", "row-1", {"platform": "web"})
    assert err.value.code == "invalid_platform"


def test_squatting_another_users_row_id_is_rejected_and_the_victim_is_unharmed(route, session):
    victim_id = device_row_id("u2", "phone-1")
    with pytest.raises(PushError) as err:
        run(route, session, "u1", "put", victim_id, insert(device="phone-1"))
    assert err.value.code == "not_device_owner" and verdict_for(err.value) == ("forbidden", "not_device_owner")
    assert all_rows(session) == []
    with pytest.raises(PushError):  # any id that is not the caller's own formula id
        run(route, session, "u1", "put", "d_" + "0" * 32, insert())
    register_device(session, PushDevice, user_id="u2", device_id="phone-1", token="v", platform="ios",
                    environment="sandbox", topic=None, now=NOW)  # the victim registers fine
    run(route, session, "u2", "put", victim_id, insert(device="phone-1", token="v2"))  # and syncs fine
    (row,) = all_rows(session)
    assert (row.id, row.user_id, row.token) == (victim_id, "u2", "v2")


def test_patch_and_delete_of_a_missing_squat_id_do_nothing_harmful(route, session):
    with pytest.raises(PushError):
        run(route, session, "u1", "patch", device_row_id("u2", "phone-1"), {"token": "x"})
    run(route, session, "u1", "delete", device_row_id("u2", "phone-1"))
    assert all_rows(session) == []


def test_honest_row_stays_patchable_and_deletable(route, session):
    run(route, session, "u1", "put", device_row_id("u1", "d1"), insert())
    run(route, session, "u1", "patch", device_row_id("u1", "d1"), {"token": "n"})
    assert all_rows(session)[0].token == "n"
    run(route, session, "u1", "delete", device_row_id("u1", "d1"))
    assert all_rows(session) == []


def test_patch_can_clear_the_topic(route, session):
    run(route, session, "u1", "put", "row-1", insert())
    run(route, session, "u1", "patch", "row-1", {"topic": ""})
    assert all_rows(session)[0].topic is None


def test_rest_register_then_the_phones_formula_put_addresses_the_same_row(route, session):
    rest = register_device(session, PushDevice, user_id="u1", device_id="d1", token="tok0", platform="ios",
                           environment="sandbox", topic=None, now=NOW)
    phone_id = device_row_id("u1", "d1")
    assert rest.id == phone_id
    run(route, session, "u1", "put", phone_id, insert())
    run(route, session, "u1", "patch", phone_id, {"token": "tok5"})
    (row,) = all_rows(session)
    assert row is rest and row.id == phone_id and row.token == "tok5"


def test_phone_put_with_the_formula_id_then_rest_register_is_one_row(route, session):
    run(route, session, "u1", "put", device_row_id("u1", "d1"), insert())
    register_device(session, PushDevice, user_id="u1", device_id="d1", token="tok9", platform="ios",
                    environment="sandbox", topic=None, now=NOW)
    (row,) = all_rows(session)
    assert row.id == device_row_id("u1", "d1")


def test_put_with_the_phones_row_id_after_a_legacy_random_id_keeps_one_row_and_the_old_id(route, session):
    old = register_device(session, PushDevice, user_id="u1", device_id="d1", token="tok0", platform="ios",
                          environment="sandbox", topic=None, now=NOW, row_id="legacy-random-id")
    run(route, session, "u1", "put", device_row_id("u1", "d1"), insert())
    (row,) = all_rows(session)
    assert row is old and row.token == "tok1" and row.id == "legacy-random-id"


def test_rest_registration_after_the_phones_put_keeps_one_row_and_the_phones_id(route, session):
    phone_id = device_row_id("u1", "d1")
    run(route, session, "u1", "put", phone_id, insert())
    register_device(session, PushDevice, user_id="u1", device_id="d1", token="tok9", platform="ios",
                    environment="production", topic=None, now=NOW)
    (row,) = all_rows(session)
    assert row.id == phone_id and row.token == "tok9"


def test_patch_without_token_just_touches_last_seen(route, session):
    run(route, session, "u1", "put", "row-1", insert())
    run(route, session, "u1", "patch", "row-1", {})
    assert all_rows(session)[0].token == "tok1"


def test_patch_token_collision_moves_the_token(route, session):
    run(route, session, "u1", "put", "row-1", insert())
    run(route, session, "u2", "put", "row-2", insert(device="d2", token="tok2"))
    run(route, session, "u2", "patch", "row-2", {"token": "tok1"})
    assert [(r.id, r.token) for r in all_rows(session)] == [(real("row-2"), "tok1")]


def test_patch_another_users_or_missing_row(route, session):
    run(route, session, "u1", "put", "row-1", insert())
    with pytest.raises(PushError) as err:
        run(route, session, "u2", "patch", "row-1", {"token": "stolen"})
    assert verdict_for(err.value) == ("forbidden", "not_device_owner")
    assert all_rows(session)[0].token == "tok1"
    with pytest.raises(PushError) as err:
        run(route, session, "u1", "patch", "nope", {"token": "x"})
    assert verdict_for(err.value) == ("not_found", "device_not_found")
    with pytest.raises(PushError) as err:
        run(route, session, "u1", "patch", "row-1", {"token": ""})
    assert err.value.code == "token_required"


def test_delete_own_row_and_gone_row(route, session):
    run(route, session, "u1", "put", "row-1", insert())
    run(route, session, "u1", "delete", "row-1")
    assert all_rows(session) == []
    run(route, session, "u1", "delete", "row-1")  # silently fine


def test_delete_another_users_row_is_refused(route, session):
    run(route, session, "u1", "put", "row-1", insert())
    with pytest.raises(PushError):
        run(route, session, "u2", "delete", "row-1")
    assert len(all_rows(session)) == 1


def test_verdict_for_ignores_other_exceptions():
    assert verdict_for(ValueError("x")) is None
    assert verdict_for(PushError("device_conflict")) == ("conflict", "device_conflict")
