"""Google OAuth2 (authorization code + PKCE S256, offline access)."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx

from bond_oauth.providers import TokenSet, get_json, post_form, token_set

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"


class GoogleOAuth:
    def __init__(self, client_id: str, client_secret: str, http: httpx.Client) -> None:
        self._id, self._secret, self._http = client_id, client_secret, http

    def authorize_url(self, *, state: str, challenge: str, scopes: list[str], redirect_uri: str,
                      offline: bool = True, prompt: str | None = None, nonce: str | None = None,
                      login_hint: str | None = None) -> str:
        """``offline`` (a connection) asks for a refresh token: ``access_type=offline``, ``prompt=consent`` and
        ``include_granted_scopes=true``. Not offline (an identity-only sign-in) is ``access_type=online`` with
        ``prompt=select_account``, so a login never mints a refresh token. ``prompt`` overrides either default."""
        params = {
            "client_id": self._id, "redirect_uri": redirect_uri, "response_type": "code",
            "scope": " ".join(scopes), "state": state, "code_challenge": challenge,
            "code_challenge_method": "S256"}
        if offline:
            params.update({"access_type": "offline", "prompt": prompt or "consent", "include_granted_scopes": "true"})
        else:
            params.update({"access_type": "online", "prompt": prompt or "select_account"})
        if nonce:
            params["nonce"] = nonce
        if login_hint:
            params["login_hint"] = login_hint
        return AUTH_URL + "?" + urlencode(params)

    def exchange(self, *, code: str, verifier: str, redirect_uri: str) -> TokenSet:
        return token_set(post_form(self._http, TOKEN_URL, {
            "code": code, "client_id": self._id, "client_secret": self._secret, "redirect_uri": redirect_uri,
            "grant_type": "authorization_code", "code_verifier": verifier}))

    def refresh(self, refresh_token: str, *, scopes: list[str]) -> TokenSet:
        data = {"client_id": self._id, "client_secret": self._secret, "refresh_token": refresh_token,
                "grant_type": "refresh_token"}
        if scopes:
            data["scope"] = " ".join(scopes)
        return token_set(post_form(self._http, TOKEN_URL, data))

    def revoke(self, token: str) -> None:
        post_form(self._http, REVOKE_URL, {"token": token})

    def userinfo(self, access_token: str) -> dict[str, Any]:
        return get_json(self._http, USERINFO_URL, access_token)
