"""Scope sets, the identity-only test, and authorize parameters for sign-in versus connect."""

from urllib.parse import parse_qs, urlparse

import pytest
from jwt_util import TID, google, microsoft

from bond_oauth import (
    GOOGLE_CALENDAR,
    GOOGLE_MAIL_SEND,
    GOOGLE_SIGNIN,
    MICROSOFT_SIGNIN,
    MICROSOFT_SIGNIN_FULL,
    FakeOAuth,
    MicrosoftOAuth,
    is_identity_only,
)


def query(url):
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


def test_named_signin_sets():
    assert GOOGLE_SIGNIN == ("openid", "email", "profile") and MICROSOFT_SIGNIN == ("openid", "profile", "email")
    assert MICROSOFT_SIGNIN_FULL == MICROSOFT_SIGNIN + (
        "offline_access", "User.Read", "Mail.Send", "Mail.Read", "Calendars.ReadWrite")
    assert GOOGLE_MAIL_SEND == ("https://www.googleapis.com/auth/gmail.send",)
    assert GOOGLE_CALENDAR == ("https://www.googleapis.com/auth/calendar.events",)


@pytest.mark.parametrize("scopes,expected", [
    (["openid", "email", "profile"], True),
    (["openid"], True),
    (["https://www.googleapis.com/auth/userinfo.email", "openid"], True),
    (["openid", "email", *GOOGLE_MAIL_SEND], False),
    (["openid", *GOOGLE_CALENDAR], False),
    (["openid", "User.Read"], False),  # not an identity scope for Google
    (["openid", "offline_access"], False),
])
def test_identity_only_google(scopes, expected):
    assert is_identity_only("google", scopes) is expected
    assert is_identity_only("fake-google", scopes) is expected


@pytest.mark.parametrize("scopes,expected", [
    (["openid", "profile", "email"], True),
    (["openid", "profile", "email", "User.Read"], True),
    (["https://graph.microsoft.com/User.Read", "openid"], True),
    (["openid", "offline_access"], False),
    (["openid", "User.Read", "offline_access"], False),
    (["openid", "Mail.Read"], False),
    (list(MICROSOFT_SIGNIN_FULL), False),
])
def test_identity_only_microsoft(scopes, expected):
    assert is_identity_only("microsoft", scopes) is expected
    assert is_identity_only("fake-microsoft", scopes) is expected


def test_google_signin_asks_online_and_select_account():
    q = query(google().authorize_url(state="S", challenge="C", scopes=["openid"], redirect_uri="r", offline=False,
                                     nonce="N"))
    assert q["access_type"] == "online" and q["prompt"] == "select_account" and q["nonce"] == "N"
    assert "include_granted_scopes" not in q


def test_google_connect_keeps_offline_consent_and_granted_scopes():
    q = query(google().authorize_url(state="S", challenge="C", scopes=["openid"], redirect_uri="r"))
    assert (q["access_type"], q["prompt"], q["include_granted_scopes"]) == ("offline", "consent", "true")
    assert "nonce" not in q and "login_hint" not in q


def test_google_prompt_override_and_login_hint():
    online = query(google().authorize_url(state="S", challenge="C", scopes=[], redirect_uri="r", offline=False,
                                          prompt="none", login_hint="a@example.com"))
    offline = query(google().authorize_url(state="S", challenge="C", scopes=[], redirect_uri="r", prompt="select_account"))
    assert online["prompt"] == "none" and online["login_hint"] == "a@example.com"
    assert offline["prompt"] == "select_account" and offline["access_type"] == "offline"


def test_microsoft_passes_prompt_nonce_and_hint_and_defaults_to_none():
    q = query(microsoft().authorize_url(state="S", challenge="C", scopes=["openid"], redirect_uri="r",
                                        prompt="select_account", nonce="N", login_hint="a@example.org"))
    assert (q["prompt"], q["nonce"], q["login_hint"]) == ("select_account", "N", "a@example.org")
    plain = query(microsoft().authorize_url(state="S", challenge="C", scopes=["openid"], redirect_uri="r"))
    assert not {"prompt", "nonce", "login_hint"} & set(plain)


def test_microsoft_pinned_tenant_is_stored_and_defaults_to_none():
    assert microsoft(TID).pinned_tenant == TID
    assert microsoft(None).pinned_tenant is None


@pytest.mark.parametrize("bad", ["common", "organizations", "consumers", "", "tid-1"])
def test_microsoft_pinned_tenant_must_be_a_guid(bad):
    import httpx
    with pytest.raises(ValueError):
        MicrosoftOAuth("c", "s", http=httpx.Client(), pinned_tenant=bad)


def test_fake_passes_login_hint_as_hint_and_keeps_the_plain_url():
    fake = FakeOAuth("/c")
    assert fake.authorize_url(state="S", challenge="C", scopes=[], redirect_uri="r") == "/c?state=S"
    assert query(fake.authorize_url(state="S", challenge="C", scopes=[], redirect_uri="r",
                                    login_hint="a@example.com"))["hint"] == "a@example.com"
