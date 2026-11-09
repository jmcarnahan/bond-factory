"""The fake's identities, declines, id_token and refresh-token rule."""

import base64
import json

import pytest

from bond_oauth import FakeOAuth, OAuthError, identity_from_token_response, pkce
from bond_oauth.fake import FAKE_TENANT, mock_code

V = "verifier-1"


def asked(fake, scopes, **kw):
    fake.authorize_url(state="S", challenge=pkce.challenge(V), scopes=scopes, redirect_uri="r", **kw)


def exchange(fake, code="mock"):
    return fake.exchange(code=code, verifier=V, redirect_uri="r")


def claims_of(tokens):
    seg = tokens.raw["id_token"].split(".")[1]
    return json.loads(base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4)))


def test_plain_mock_uses_the_configured_email_and_still_works():
    fake = FakeOAuth("/c", email="cfg@example.com")
    asked(fake, ["a"])
    tokens = exchange(fake)
    assert claims_of(tokens)["email"] == "cfg@example.com" and fake.userinfo(tokens.access_token)["email"] == "cfg@example.com"


def test_default_email_is_demo():
    fake = FakeOAuth("/c")
    asked(fake, ["a"])
    assert claims_of(exchange(fake))["email"] == "demo@example.com"


def test_code_with_an_email_sets_the_identity():
    fake = FakeOAuth("/c")
    asked(fake, ["a"])
    tokens = exchange(fake, mock_code("OTHER@example.com"))
    assert claims_of(tokens)["email"] == "OTHER@example.com" and fake.userinfo(tokens.access_token)["name"] == "OTHER"


def test_the_subject_is_stable_per_email_and_differs_between_emails():
    fake = FakeOAuth("/c")
    subs = []
    for email in ("a@example.com", "a@example.com", "b@example.com"):
        asked(fake, ["a"])
        subs.append(claims_of(exchange(fake, mock_code(email)))["sub"])
    assert subs[0] == subs[1] != subs[2] and subs[0].startswith("fake-") and len(subs[0]) == 17


@pytest.mark.parametrize("code", ["nope", "mock:", "mock:@@@", "mockery"])
def test_unknown_or_damaged_codes_are_invalid(code):
    fake = FakeOAuth("/c")
    asked(fake, ["a"])
    with pytest.raises(OAuthError) as caught:
        exchange(fake, code)
    assert caught.value.code == "invalid_code"


def test_decline_removes_a_sets_scopes_but_never_identity_scopes():
    fake = FakeOAuth("/c", set_scopes={"mail": ["m.send", "openid"], "cal": ["c.events"]})
    asked(fake, ["openid", "email", "m.send", "c.events"])
    tokens = exchange(fake, mock_code("a@example.com", ["mail", "unknown"]))
    assert tokens.scope == "openid email c.events"


def test_declining_two_sets():
    fake = FakeOAuth("/c", set_scopes={"mail": ["m.send"], "cal": ["c.events"]})
    asked(fake, ["openid", "m.send", "c.events"])
    assert exchange(fake, mock_code("a@example.com", ["mail", "cal"])).scope == "openid"


def test_id_token_has_the_contract_claims_and_nonce():
    fake = FakeOAuth("/c", client_id="cid-9")
    asked(fake, ["openid"], nonce="N1")
    tokens = exchange(fake, mock_code("a@example.com"))
    header = json.loads(base64.urlsafe_b64decode(tokens.raw["id_token"].split(".")[0] + "=="))
    claims = claims_of(tokens)
    assert header == {"alg": "none", "typ": "JWT"} and tokens.raw["id_token"].endswith(".")
    assert (claims["iss"], claims["aud"], claims["nonce"], claims["email_verified"]) == (
        "https://fake.invalid", "cid-9", "N1", True)
    assert claims["exp"] > claims["iat"] and "tid" not in claims


def test_no_nonce_claim_when_none_was_sent():
    fake = FakeOAuth("/c")
    asked(fake, ["openid"])
    assert "nonce" not in claims_of(exchange(fake))


def test_microsoft_kind_adds_tenant_oid_and_username():
    fake = FakeOAuth("/c", kind="microsoft")
    asked(fake, ["openid"])
    claims = claims_of(exchange(fake, mock_code("a@example.org")))
    assert claims["tid"] == FAKE_TENANT and claims["preferred_username"] == "a@example.org" and claims["oid"]
    pinned = FakeOAuth("/c", kind="microsoft", pinned_tenant="tid-x")
    asked(pinned, ["openid"])
    assert claims_of(exchange(pinned))["tid"] == "tid-x"


def test_the_fake_identity_passes_through_identity_from_token_response():
    fake = FakeOAuth("/c", client_id="cid")
    asked(fake, ["openid"], nonce="N")
    tokens = exchange(fake, mock_code("a@example.com"))
    who = identity_from_token_response("fake-google", fake, tokens, expected_nonce="N", client_id="cid")
    assert who.email == "a@example.com" and who.email_verified and who.subject.startswith("fake-")


def test_google_refresh_token_only_for_an_offline_flow():
    fake = FakeOAuth("/c")
    asked(fake, ["openid"], offline=False)
    assert exchange(fake).refresh_token is None
    asked(fake, ["openid"], offline=True)
    assert exchange(fake).refresh_token


def test_microsoft_refresh_token_only_with_offline_access():
    fake = FakeOAuth("/c", kind="microsoft")
    asked(fake, ["openid", "User.Read"])
    assert exchange(fake).refresh_token is None
    asked(fake, ["openid", "offline_access"])
    tokens = exchange(fake)
    assert tokens.refresh_token and fake.refresh(tokens.refresh_token, scopes=[]).scope == "openid offline_access"


def test_unsigned_ids_ok_is_an_instance_flag():
    assert FakeOAuth("/c").unsigned_ids_ok is True
