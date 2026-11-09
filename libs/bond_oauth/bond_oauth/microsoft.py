"""Microsoft identity platform v2 (authorization code + PKCE S256)."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx

from bond_oauth.providers import TokenSet, get_json, post_form, token_set

LOGIN = "https://login.microsoftonline.com"
ME_URL = "https://graph.microsoft.com/v1.0/me"


class MicrosoftOAuth:
    def __init__(self, client_id: str, client_secret: str, tenant: str = "common",
                 http: httpx.Client | None = None) -> None:
        if http is None:
            raise ValueError("pass an httpx.Client (set its timeout there)")
        self._id, self._secret, self._tenant, self._http = client_id, client_secret, tenant, http

    def _endpoint(self, leaf: str) -> str:
        return f"{LOGIN}/{self._tenant}/oauth2/v2.0/{leaf}"

    def authorize_url(self, *, state: str, challenge: str, scopes: list[str], redirect_uri: str) -> str:
        return self._endpoint("authorize") + "?" + urlencode({
            "client_id": self._id, "response_type": "code", "redirect_uri": redirect_uri,
            "response_mode": "query", "scope": " ".join(scopes), "state": state,
            "code_challenge": challenge, "code_challenge_method": "S256"})

    def exchange(self, *, code: str, verifier: str, redirect_uri: str) -> TokenSet:
        return token_set(post_form(self._http, self._endpoint("token"), {
            "client_id": self._id, "client_secret": self._secret, "code": code, "redirect_uri": redirect_uri,
            "grant_type": "authorization_code", "code_verifier": verifier}))

    def refresh(self, refresh_token: str, *, scopes: list[str]) -> TokenSet:
        """Pass the STORED scopes: asking for scopes the person never granted fails the refresh. With none stored
        the parameter is left out and the provider re-issues what was consented to."""
        data = {"client_id": self._id, "client_secret": self._secret, "refresh_token": refresh_token,
                "grant_type": "refresh_token"}
        if scopes:
            data["scope"] = " ".join(scopes)
        return token_set(post_form(self._http, self._endpoint("token"), data))

    def revoke(self, token: str) -> None:
        """The platform has no per-token revocation call; the connection is closed on our side only."""

    def userinfo(self, access_token: str) -> dict[str, Any]:
        body = get_json(self._http, ME_URL, access_token)
        email = body.get("mail") or body.get("userPrincipalName") or ""
        return {"email": email, "name": body.get("displayName"), "id": body.get("id")}
