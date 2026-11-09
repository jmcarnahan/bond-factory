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

    def authorize_url(self, *, state: str, challenge: str, scopes: list[str], redirect_uri: str) -> str:
        return AUTH_URL + "?" + urlencode({
            "client_id": self._id, "redirect_uri": redirect_uri, "response_type": "code",
            "scope": " ".join(scopes), "state": state, "code_challenge": challenge,
            "code_challenge_method": "S256", "access_type": "offline", "prompt": "consent",
            "include_granted_scopes": "true"})

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
