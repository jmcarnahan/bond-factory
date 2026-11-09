# ruff: noqa: F811
"""Protocol conformance, refresh rotation and reuse, revoke-all, providers."""

from __future__ import annotations

import inspect
from dataclasses import fields, is_dataclass

import bond_signin as sig
from bond_auth_py import SessionSpec as RealSpec
from bond_auth_py import SessionStore
from bond_auth_py.sessions import IssuedSession as RealIssued
from bond_oauth import HandoffStore, SignInFlow
from bond_signin import protocols as P
from signin_conformance_support import (  # noqa: F401
    GOOGLE,
    MICROSOFT,
    ORIGIN,
    AuthSession,
    Directory,
    User,
    client,
    code_of,
    redeem_pair,
    stack,
    web_sign_in,
)
from sqlalchemy import select

# 1. structural -------------------------------------------------------------------------------------------------


def _params(fn):
    sig_ = inspect.signature(fn)
    return {n: p for n, p in sig_.parameters.items() if n != "self"}


def compare_methods(proto, real) -> list[str]:
    """Mismatches of every public Protocol method against ``real``: missing, missing/extra parameter names,
    keyword-only in the Protocol but positional-only in the real one, extra REQUIRED real parameters."""
    problems: list[str] = []
    for name, member in vars(proto).items():
        if name.startswith("_") or not callable(member):
            continue
        impl = getattr(real, name, None)
        if impl is None:
            problems.append(f"{proto.__name__}.{name}: missing on {type(real).__name__}")
            continue
        want, have = _params(member), _params(impl)
        if "session" in want and next(iter(want)) == "session" and have:
            have = {("session" if i == 0 else n): q for i, (n, q) in enumerate(have.items())}  # passed positionally
        has_var_kw = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in have.values())
        for pname, p in want.items():
            if pname not in have and not has_var_kw:
                problems.append(f"{proto.__name__}.{name}: parameter {pname!r} missing on the real method")
            elif pname in have and have[pname].kind is inspect.Parameter.POSITIONAL_ONLY:
                problems.append(f"{proto.__name__}.{name}: parameter {pname!r} is positional-only in the real one")
        for pname, p in have.items():
            required = p.default is inspect.Parameter.empty and p.kind in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
            if pname not in want and required:
                problems.append(f"{proto.__name__}.{name}: real method REQUIRES parameter {pname!r} the Protocol lacks")
    return problems


def compare_shape(proto, real_cls) -> list[str]:
    names = {f.name for f in fields(real_cls)} if is_dataclass(real_cls) else set(dir(real_cls))
    return [f"{proto.__name__}.{n}: missing on {real_cls.__name__}" for n in getattr(proto, "__annotations__", {})
            if n not in names]


def test_protocols_are_satisfied_by_the_real_objects(stack):
    assert isinstance(stack.flow, P.IdentityFlow)
    assert isinstance(stack.handoffs, P.HandoffStore)
    assert isinstance(stack.store, P.SessionIssuer)
    assert isinstance(stack.directory, P.UserDirectory)
    problems = [*compare_methods(P.IdentityFlow, stack.flow), *compare_methods(P.HandoffStore, stack.handoffs),
                *compare_methods(P.SessionIssuer, stack.store), *compare_methods(P.UserDirectory, stack.directory)]
    assert not problems, "\n".join(problems)


def test_value_shapes_match_the_protocols(stack, client):
    from bond_oauth import OidcIdentity, SignInResult, StartedSignIn, StateInfo

    problems = [*compare_shape(P.OidcIdentity, OidcIdentity), *compare_shape(P.SignInResult, SignInResult),
                *compare_shape(P.StartedSignIn, StartedSignIn), *compare_shape(P.StateInfo, StateInfo),
                *compare_shape(P.SessionSpec, RealSpec), *compare_shape(P.IssuedSession, RealIssued)]
    assert not problems, "\n".join(problems)
    assert [f.name for f in fields(P.SessionSpec)] == [f.name for f in fields(RealSpec)]
    assert [f.name for f in fields(P.IssuedSession)] == [f.name for f in fields(RealIssued)]
    assert isinstance(stack.flow, SignInFlow) and isinstance(stack.handoffs, HandoffStore)
    assert isinstance(stack.store, SessionStore)




# 6. refresh via body, reuse ------------------------------------------------------------------------------------


def test_body_refresh_rotates_and_reuse_kills_the_family(stack, client):
    first = redeem_pair(client)
    r1 = client.post("/auth/refresh", json={"refresh_token": first["refresh_token"], "rotation_id": "rot-1",
                                            "delivery": "body"})
    assert r1.status_code == 200, r1.text
    second = r1.json()
    assert second["refresh_token"] and second["refresh_token"] != first["refresh_token"] and second["token"]
    assert second["user"]["id"] == "u-google" and not r1.headers.get_list("set-cookie")

    stack.sessions.offset = 60.0  # past the 20 s grace window (the clock the lib reads, no sleeping)
    replay = client.post("/auth/refresh", json={"refresh_token": first["refresh_token"], "rotation_id": "rot-other",
                                                "delivery": "body"})
    assert replay.status_code == 401 and code_of(replay) == "refresh_reused"

    dead = client.post("/auth/refresh", json={"refresh_token": second["refresh_token"], "rotation_id": "rot-2",
                                              "delivery": "body"})
    assert dead.status_code == 401 and code_of(dead) in ("refresh_revoked", "refresh_reused")
    with stack.db() as s:
        reasons = {r.revoke_reason for r in s.scalars(select(AuthSession)) if r.revoked_at}
        assert "reuse" in reasons


def test_lost_response_retry_with_the_same_rotation_id_is_served(stack, client):
    first = redeem_pair(client)
    body = {"refresh_token": first["refresh_token"], "rotation_id": "rot-same", "delivery": "body"}
    a = client.post("/auth/refresh", json=body)
    stack.sessions.offset = 60.0
    b = client.post("/auth/refresh", json=body)  # the client never saw answer a: same id, child still unused
    assert a.status_code == 200 and b.status_code == 200, b.text
    assert b.json()["refresh_token"] != a.json()["refresh_token"]


def test_refresh_without_a_token_is_401(client):
    r = client.post("/auth/refresh", json={}, headers=ORIGIN)
    assert r.status_code == 401 and code_of(r) == "invalid_token"


def test_cookie_refresh_needs_an_origin(stack, client):
    web_sign_in(client)
    assert client.post("/auth/refresh", json={}).status_code == 403


def test_revoke_all_marks_sessions_invalid(stack, client):
    web_sign_in(client)
    r = client.post("/auth/sessions/revoke-all", json={}, headers=ORIGIN)
    assert r.status_code == 200 and r.json()["revoked"] >= 1
    with stack.db() as s:
        assert s.get(User, "u-google").sessions_valid_after is not None


# 7. providers --------------------------------------------------------------------------------------------------


def test_providers_lists_both_sign_in_fakes(client):
    body = client.get("/auth/providers").json()
    assert [p["id"] for p in body["signin"]] == [GOOGLE, MICROSOFT]
    assert body["signin"][0]["label"] == "Fake Google"
    assert body["break_glass"] is False and body["default_flow"] == "signin"


def test_return_page_is_served(client):
    r = client.get(f"/app/return/{GOOGLE}")
    assert r.status_code == 200 and "Return to the app" in r.text


def test_directory_fake_is_a_user_directory():
    assert isinstance(Directory(), P.UserDirectory) and sig.UserDirectory is P.UserDirectory


def test_cookie_sourced_refresh_always_answers_with_cookies(stack, client):
    web_sign_in(client)
    r = client.post("/auth/refresh", json={"delivery": "body"}, headers=ORIGIN)  # no body token: the cookie decides
    assert r.status_code == 200, r.text
    assert "refresh_token" not in r.json()
    names = {c.split("=", 1)[0] for c in r.headers.get_list("set-cookie")}
    assert {"conf_access_token", "conf_refresh_token"} <= names
    assert client.post("/auth/refresh", json={"delivery": "body"}).status_code == 403  # and it needs an Origin


def test_body_token_with_delivery_cookie_needs_an_origin(stack, client):
    pair = redeem_pair(client)
    body = {"refresh_token": pair["refresh_token"], "rotation_id": "r-1", "delivery": "cookie"}
    assert client.post("/auth/refresh", json=body).status_code == 403


def test_legacy_id_token_refresh_needs_an_origin_unless_a_bearer_is_present(stack, client):
    body = {"id_token": "legacy"}
    no_origin = client.post("/auth/refresh", json=body)
    assert no_origin.status_code == 403 and code_of(no_origin) == "invalid_origin"
    ok = client.post("/auth/refresh", json=body, headers=ORIGIN)
    assert ok.status_code == 200 and ok.json() == {"legacy": True}
    bearer = client.post("/auth/refresh", json=body, headers={"Authorization": "Bearer abc"})
    assert bearer.status_code == 200 and bearer.json() == {"legacy": True}
