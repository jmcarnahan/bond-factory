"""Microsoft identity platform v2 (authorization code + PKCE S256)."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx

from bond_oauth.guid import GUID
from bond_oauth.providers import TokenSet, get_json, post_form, token_set

LOGIN = "https://login.microsoftonline.com"
ME_URL = "https://graph.microsoft.com/v1.0/me?$select=id,displayName,mail,userPrincipalName,userType"  # userType is not a default field


class MicrosoftOAuth:
    def __init__(self, client_id: str, client_secret: str, tenant: str = "common",
                 http: httpx.Client | None = None, pinned_tenant: str | None = None) -> None:
        if http is None:
            raise ValueError("pass an httpx.Client (set its timeout there)")
        self._id, self._secret, self._tenant, self._http = client_id, client_secret, tenant, http
        if pinned_tenant is not None and not GUID.match(pinned_tenant):
            raise ValueError("pinned_tenant must be a tenant GUID (not common, organizations or consumers)")
        self.pinned_tenant = pinned_tenant  # sign-in accepts only this tenant id (``identity.py``)

    def _endpoint(self, leaf: str) -> str:
        return f"{LOGIN}/{self._tenant}/oauth2/v2.0/{leaf}"

    def authorize_url(self, *, state: str, challenge: str, scopes: list[str], redirect_uri: str,
                      offline: bool = True, prompt: str | None = None, nonce: str | None = None,
                      login_hint: str | None = None) -> str:
        """``prompt`` is passed through (none for a connect; a sign-in passes ``select_account``). Refresh tokens
        come from the ``offline_access`` scope, so ``offline`` changes nothing here."""
        params = {
            "client_id": self._id, "response_type": "code", "redirect_uri": redirect_uri,
            "response_mode": "query", "scope": " ".join(scopes), "state": state,
            "code_challenge": challenge, "code_challenge_method": "S256"}
        for key, value in (("prompt", prompt), ("nonce", nonce), ("login_hint", login_hint)):
            if value:
                params[key] = value
        return self._endpoint("authorize") + "?" + urlencode(params)

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
        return {"email": email, "mail": body.get("mail") or "",
                "upn": body.get("userPrincipalName") or "", "user_type": body.get("userType") or "", "name": body.get("displayName"),
                "id": body.get("id")}
