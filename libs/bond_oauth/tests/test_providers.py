import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from bond_oauth import GoogleOAuth, MicrosoftOAuth, ProviderError, RetryableError, pkce


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def form(request):
    return {k: v[0] for k, v in parse_qs(request.content.decode()).items()}


def test_google_authorize_url_params():
    google = GoogleOAuth("cid", "sec", client(lambda r: httpx.Response(500)))
    url = google.authorize_url(state="S", challenge=pkce.challenge("v"), scopes=["openid", "email"],
                               redirect_uri="http://cb/x")
    parts = urlparse(url)
    q = {k: v[0] for k, v in parse_qs(parts.query).items()}
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == "https://accounts.google.com/o/oauth2/v2/auth"
    assert q["access_type"] == "offline" and q["prompt"] == "consent" and q["include_granted_scopes"] == "true"
    assert q["code_challenge"] == pkce.challenge("v") and q["code_challenge_method"] == "S256"
    assert q["scope"] == "openid email" and q["state"] == "S" and q["response_type"] == "code"
    assert q["redirect_uri"] == "http://cb/x" and q["client_id"] == "cid"


def test_microsoft_authorize_url_params():
    ms = MicrosoftOAuth("cid", "sec", tenant="t-1", http=client(lambda r: httpx.Response(500)))
    url = ms.authorize_url(state="S", challenge="C", scopes=["Mail.Send", "offline_access"], redirect_uri="http://cb")
    parts = urlparse(url)
    q = {k: v[0] for k, v in parse_qs(parts.query).items()}
    assert parts.path == "/t-1/oauth2/v2.0/authorize" and parts.netloc == "login.microsoftonline.com"
    assert q["response_mode"] == "query" and q["code_challenge_method"] == "S256" and q["code_challenge"] == "C"
    assert q["scope"] == "Mail.Send offline_access"


def test_microsoft_default_tenant_is_common():
    ms = MicrosoftOAuth("cid", "sec", http=client(lambda r: httpx.Response(500)))
    assert "/common/oauth2/v2.0/authorize" in ms.authorize_url(state="s", challenge="c", scopes=[], redirect_uri="r")


def test_google_exchange_sends_verifier_and_parses_tokens():
    seen = {}

    def handler(request):
        seen.update(form(request), url=str(request.url))
        return httpx.Response(200, json={"access_token": "a", "refresh_token": "r", "expires_in": 3599,
                                         "scope": "openid email", "token_type": "Bearer"})

    tokens = GoogleOAuth("cid", "sec", client(handler)).exchange(code="C", verifier="V", redirect_uri="http://cb")
    assert seen["url"] == "https://oauth2.googleapis.com/token"
    assert seen["code_verifier"] == "V" and seen["grant_type"] == "authorization_code" and seen["code"] == "C"
    assert (tokens.access_token, tokens.refresh_token, tokens.expires_in, tokens.scope) == (
        "a", "r", 3599, "openid email")


def test_microsoft_exchange_hits_tenant_token_endpoint():
    seen = {}

    def handler(request):
        seen.update(form(request), url=str(request.url))
        return httpx.Response(200, json={"access_token": "a", "refresh_token": "r", "expires_in": 3600, "scope": "x"})

    MicrosoftOAuth("cid", "sec", tenant="t", http=client(handler)).exchange(code="C", verifier="V", redirect_uri="u")
    assert seen["url"] == "https://login.microsoftonline.com/t/oauth2/v2.0/token" and seen["code_verifier"] == "V"


def test_refresh_passes_stored_scopes_and_omits_when_none():
    bodies = []

    def handler(request):
        bodies.append(form(request))
        return httpx.Response(200, json={"access_token": "n", "expires_in": 60})

    ms = MicrosoftOAuth("cid", "sec", http=client(handler))
    ms.refresh("rt", scopes=["Mail.Read", "User.Read"])
    ms.refresh("rt", scopes=[])
    assert bodies[0]["scope"] == "Mail.Read User.Read" and bodies[0]["grant_type"] == "refresh_token"
    assert "scope" not in bodies[1]


def test_refresh_invalid_grant_is_provider_error():
    handler = lambda r: httpx.Response(400, json={"error": "invalid_grant", "error_description": "gone"})
    with pytest.raises(ProviderError) as err:
        GoogleOAuth("c", "s", client(handler)).refresh("rt", scopes=[])
    assert err.value.code == "invalid_grant" and err.value.status == 400


def test_refresh_401_is_provider_error_with_status():
    with pytest.raises(ProviderError) as err:
        GoogleOAuth("c", "s", client(lambda r: httpx.Response(401, text="no"))).refresh("rt", scopes=[])
    assert err.value.status == 401


def test_5xx_and_timeout_are_retryable():
    with pytest.raises(RetryableError):
        GoogleOAuth("c", "s", client(lambda r: httpx.Response(503))).refresh("rt", scopes=[])

    def boom(request):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(RetryableError):
        MicrosoftOAuth("c", "s", http=client(boom)).refresh("rt", scopes=[])


def test_token_answer_without_access_token_is_an_error():
    with pytest.raises(ProviderError) as err:
        GoogleOAuth("c", "s", client(lambda r: httpx.Response(200, json={}))).refresh("rt", scopes=[])
    assert err.value.code == "invalid_response"


def test_google_userinfo_and_revoke():
    calls = []

    def handler(request):
        calls.append((request.method, str(request.url), request.headers.get("authorization"), request.content))
        if request.url.host == "openidconnect.googleapis.com":
            return httpx.Response(200, json={"email": "a@example.com", "sub": "1"})
        return httpx.Response(200, json={})

    google = GoogleOAuth("c", "s", client(handler))
    assert google.userinfo("tok")["email"] == "a@example.com"
    google.revoke("rt")
    assert calls[0][2] == "Bearer tok"
    assert calls[1][1] == "https://oauth2.googleapis.com/revoke" and b"token=rt" in calls[1][3]


def test_microsoft_userinfo_prefers_mail_then_upn():
    bodies = iter([{"mail": "m@example.com", "userPrincipalName": "u@example.com"},
                   {"mail": None, "userPrincipalName": "u@example.com"}])
    ms = MicrosoftOAuth("c", "s", http=client(lambda r: httpx.Response(200, json=next(bodies))))
    assert ms.userinfo("t")["email"] == "m@example.com"
    assert ms.userinfo("t")["email"] == "u@example.com"


def test_microsoft_revoke_makes_no_call():
    def handler(request):
        raise AssertionError("no network call expected")

    MicrosoftOAuth("c", "s", http=client(handler)).revoke("rt")


def test_userinfo_failure_status():
    with pytest.raises(ProviderError):
        GoogleOAuth("c", "s", client(lambda r: httpx.Response(403, json={}))).userinfo("t")


def test_microsoft_requires_a_client():
    with pytest.raises(ValueError):
        MicrosoftOAuth("c", "s")


def test_error_body_never_needs_to_be_json():
    with pytest.raises(ProviderError) as err:
        GoogleOAuth("c", "s", client(lambda r: httpx.Response(400, content=b"<html>"))).refresh("rt", scopes=[])
    assert err.value.code == "http_400"
    assert json.dumps(err.value.code)
