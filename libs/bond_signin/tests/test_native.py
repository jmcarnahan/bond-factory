"""Native sign-in: device-bound start, callback hand-off, redeem."""

from urllib.parse import parse_qs, urlsplit

import pytest

from .conftest import OWN_ORIGIN, native_start, sha, state_of

SECRET = "s" * 32


def query(resp) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(resp.headers["location"]).query).items()}


def callback(h, state, code="alice", provider="google"):
    return h.client.get(f"/auth/signin/{provider}/callback?state={state}&code={code}")


def test_native_start_returns_url_and_sets_no_cookie(h):
    resp = native_start(h)
    assert resp.status_code == 200 and "set-cookie" not in resp.headers
    started = h.flow.started[0]
    assert started["device_hash"] == sha(SECRET) and started["attempt_id"] == "att_1"
    assert started["redirect_to"] == f"{OWN_ORIGIN}/app/return/google"


@pytest.mark.parametrize("mutate", [
    lambda b: b.pop("device_challenge"),
    lambda b: b.update(device_challenge="AB" * 32),
    lambda b: b.update(device_challenge="a" * 63),
    lambda b: b.pop("attempt"),
    lambda b: b.update(attempt="x" * 65),
    lambda b: b.update(attempt="has space"),
    lambda b: b.update(redirect_to="https://evil.example/app/return/google"),
    lambda b: b.update(redirect_to=f"{OWN_ORIGIN}/app/return/microsoft"),
    lambda b: b.update(redirect_to=f"{OWN_ORIGIN}/app/return/google/extra"),
    lambda b: b.update(redirect_to="org.evil.app://return"),
])
def test_native_start_validation(h, mutate):
    body = {"mode": "native", "device_challenge": sha(SECRET), "attempt": "att_1",
            "redirect_to": f"{OWN_ORIGIN}/app/return/google"}
    mutate(body)
    resp = h.client.post("/auth/signin/google/start", json=body)
    assert resp.status_code == 400 and resp.json()["detail"]["code"] == "invalid_request"
    assert h.flow.started == []


def test_native_start_accepts_an_allowed_custom_scheme(h):
    resp = native_start(h, redirect_to="com.example.app://return/google")
    assert resp.status_code == 200


def test_native_start_attempt_charset_edges(h):
    assert native_start(h, attempt="A-b_9" * 12 + "abcd").status_code == 200  # 64 chars
    assert native_start(h, attempt="a" * 64).status_code == 200


def test_native_callback_redirects_with_attempt_and_code_and_sets_no_session(h):
    state = state_of(native_start(h))
    resp = callback(h, state)
    assert resp.status_code == 302
    assert resp.headers["location"].startswith(f"{OWN_ORIGIN}/app/return/google?")
    q = query(resp)
    assert q["attempt"] == "att_1" and q["code"] and "error" not in q
    assert "set-cookie" not in resp.headers and h.sessions.issued == []
    row = h.handoffs.issued[0]
    assert row["purpose"] == "signin" and row["attempt_id"] == "att_1"
    assert row["payload"] == {"user_id": "u-alice", "provider": "google", "auth_time": 1_800_000_000.0,
                              "attempt": "att_1"}
    assert h.directory.signins[0]["first"] is True


def test_native_callback_passes_the_state_device_hash_to_complete(h):
    callback(h, state_of(native_start(h)))
    assert h.flow.completed[0]["device"] == sha(SECRET) and h.flow.completed[0]["nonce"] is None


def test_native_identity_only_stores_nothing_offline_stores_one(h):
    callback(h, state_of(native_start(h)))
    assert h.flow.stored == []
    callback(h, state_of(native_start(h, provider="microsoft", attempt="att_2")), code="bob", provider="microsoft")
    assert h.flow.stored == [{"owner": "u-bob", "model": "CONN", "pending": "PENDING"}]


def test_native_refusal_returns_attempt_and_error_and_no_code(h):
    resp = callback(h, state_of(native_start(h)), code="stranger")
    q = query(resp)
    assert q == {"attempt": "att_1", "error": "not_invited"}
    assert h.handoffs.issued == [] and h.directory.refusals[0]["reason"] == "not_invited"


def test_native_access_denied(h):
    state = state_of(native_start(h))
    resp = h.client.get(f"/auth/signin/google/callback?state={state}&error=access_denied")
    assert query(resp) == {"attempt": "att_1", "error": "consent_declined"}


def redeem(h, code, secret=SECRET, **extra):
    return h.client.post("/auth/signin/redeem", json={"code": code, "device_secret": secret, **extra})


def issue_code(h, **kw):
    resp = callback(h, state_of(native_start(h, **kw)))
    return query(resp)["code"]


def test_redeem_returns_tokens_and_user_in_the_body_only(h):
    resp = redeem(h, issue_code(h), device_label="Pixel")
    body = resp.json()
    assert resp.status_code == 200 and "set-cookie" not in resp.headers
    assert body["token"].startswith("jwt-u-alice") and body["refresh_token"].startswith("rt-")
    assert body["user"]["email"] == "alice@example.com" and body["expires_in"] == 3600
    assert h.sessions.issued[0]["device_label"] == "Pixel" and h.sessions.issued[0]["provider"] == "google"


def test_redeem_is_single_use(h):
    code = issue_code(h)
    assert redeem(h, code).status_code == 200
    again = redeem(h, code)
    assert again.status_code == 401 and again.json()["detail"]["code"] == "invalid_handoff"
    assert len(h.sessions.issued) == 1


def test_redeem_wrong_secret_fails_and_burns_the_code(h):
    code = issue_code(h)
    wrong = redeem(h, code, secret="x" * 32)
    assert wrong.status_code == 401 and wrong.json()["detail"]["code"] == "invalid_handoff"
    assert redeem(h, code).status_code == 401  # burned: even the right secret fails now
    assert h.sessions.issued == []
    assert h.db.rollbacks == 0  # the burn is committed


def test_lured_victim_cannot_redeem_with_their_own_secret(h):
    code = issue_code(h)  # the attacker's attempt, sent to the victim's browser
    assert redeem(h, code, secret="v" * 32).status_code == 401 and h.sessions.issued == []


def test_redeem_unknown_code_and_bad_body(h):
    assert redeem(h, "nope").status_code == 401
    assert h.client.post("/auth/signin/redeem", json={"code": "x"}).status_code == 400
    assert h.client.post("/auth/signin/redeem", json={"code": 1, "device_secret": 2}).status_code == 400


def test_redeem_rechecks_the_user_is_still_active(h):
    code = issue_code(h)
    h.directory.by_id["u-alice"].is_active = False
    resp = redeem(h, code)
    assert resp.status_code == 403 and resp.json()["detail"]["code"] == "deactivated"
    assert h.sessions.issued == []


def test_redeem_rechecks_sessions_valid_after(h):
    from datetime import UTC, datetime
    code = issue_code(h)
    h.directory.by_id["u-alice"].sessions_valid_after = datetime.fromtimestamp(1_800_000_100, UTC).replace(tzinfo=None)
    resp = redeem(h, code)
    assert resp.status_code == 401 and resp.json()["detail"]["code"] == "session_revoked"


def test_native_expired_state_returns_attempt_and_error(h):
    state = state_of(native_start(h))
    h.flow.states[state].expired = True
    resp = callback(h, state)
    assert query(resp) == {"attempt": "att_1", "error": "signin_expired"}
    assert h.flow.completed == [] and h.handoffs.issued == []
    assert [r["reason"] for r in h.directory.refusals] == ["signin_expired"]


def test_native_state_for_another_provider_is_400(h):
    state = state_of(native_start(h))
    resp = h.client.get(f"/auth/signin/microsoft/callback?state={state}&code=alice")
    assert resp.status_code == 400 and h.flow.completed == []


def test_native_return_is_rechecked_at_callback(h):
    state = state_of(native_start(h))
    h.flow.states[state].redirect_to = "https://evil.example/app/return/google"
    resp = callback(h, state)
    assert resp.status_code == 400 and "location" not in resp.headers
    assert h.flow.completed == [] and h.handoffs.issued == []
