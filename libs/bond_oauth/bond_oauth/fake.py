"""An offline provider: the consent page is the app's own, ``exchange("mock")`` mints tokens."""

from __future__ import annotations

import secrets
from typing import Any
from urllib.parse import urlencode

from bond_oauth import pkce
from bond_oauth.errors import OAuthError, ProviderError
from bond_oauth.providers import TokenSet
from bond_oauth.scopes import split_scopes

MOCK_CODE = "mock"


class FakeOAuth:
    def __init__(self, consent_base: str, email: str = "demo@example.com") -> None:
        self.consent_base = consent_base
        self.email = email
        self.refresh_calls = 0
        self.revoked: list[str] = []
        self._requested: dict[str, list[str]] = {}  # PKCE challenge -> scopes asked for
        self._granted: dict[str, list[str]] = {}  # refresh token -> scopes
        self._fail_with: str | None = None

    def fail_refresh_with(self, error: str | None) -> None:
        """The next refreshes answer with this provider error (``None`` clears it)."""
        self._fail_with = error

    def authorize_url(self, *, state: str, challenge: str, scopes: list[str], redirect_uri: str) -> str:
        self._requested[challenge] = list(scopes)
        return f"{self.consent_base}?{urlencode({'state': state})}"

    def exchange(self, *, code: str, verifier: str, redirect_uri: str) -> TokenSet:
        scopes = self._requested.get(pkce.challenge(verifier))
        if code != MOCK_CODE or scopes is None:
            raise OAuthError("invalid_code", "The sign-in code was not accepted")
        refresh = "fake-refresh-" + secrets.token_hex(8)
        self._granted[refresh] = scopes
        return self._tokens(refresh, scopes, with_refresh=True)

    def refresh(self, refresh_token: str, *, scopes: list[str]) -> TokenSet:
        self.refresh_calls += 1
        if self._fail_with:
            raise ProviderError(self._fail_with, 400)
        granted = self._granted.get(refresh_token)
        if granted is None:
            raise ProviderError("invalid_grant", 400)
        wanted = split_scopes(scopes) or granted
        return self._tokens(refresh_token, [s for s in wanted if s in granted], with_refresh=False)

    def revoke(self, token: str) -> None:
        self.revoked.append(token)

    def userinfo(self, access_token: str) -> dict[str, Any]:
        return {"email": self.email}

    def _tokens(self, refresh: str, scopes: list[str], *, with_refresh: bool) -> TokenSet:
        body = {"access_token": "fake-access-" + secrets.token_hex(8), "expires_in": 3600,
                "scope": " ".join(scopes), "token_type": "Bearer"}
        if with_refresh:
            body["refresh_token"] = refresh
        return TokenSet(access_token=body["access_token"], refresh_token=refresh if with_refresh else None,
                        expires_in=3600, scope=body["scope"], token_type="Bearer", raw=body)
