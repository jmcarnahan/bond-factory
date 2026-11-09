"""The provider seam, the token set, and the shared form-post helper."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from bond_oauth.errors import ProviderError, RetryableError


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    refresh_token: str | None = None
    expires_in: int = 3600
    scope: str = ""
    token_type: str = "Bearer"
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


class OAuthProvider(Protocol):
    def authorize_url(self, *, state: str, challenge: str, scopes: list[str], redirect_uri: str) -> str: ...

    def exchange(self, *, code: str, verifier: str, redirect_uri: str) -> TokenSet: ...

    def refresh(self, refresh_token: str, *, scopes: list[str]) -> TokenSet: ...

    def revoke(self, token: str) -> None: ...

    def userinfo(self, access_token: str) -> dict[str, Any]: ...


def post_form(http: httpx.Client, url: str, data: dict[str, str]) -> dict[str, Any]:
    """POST a form and return the JSON body. Transport trouble and 5xx raise ``RetryableError``; any other
    non-200 raises ``ProviderError`` carrying the provider's ``error`` string and the HTTP status."""
    try:
        reply = http.post(url, data=data, headers={"Accept": "application/json"})
    except httpx.HTTPError as exc:
        raise RetryableError(f"provider did not answer ({type(exc).__name__})") from exc
    if reply.status_code >= 500:
        raise RetryableError(f"provider error {reply.status_code}")
    body = _json(reply)
    if reply.status_code != 200:
        raise ProviderError(str(body.get("error") or f"http_{reply.status_code}"), reply.status_code,
                            str(body.get("error_description") or "")[:200] or None)
    return body


def get_json(http: httpx.Client, url: str, access_token: str) -> dict[str, Any]:
    try:
        reply = http.get(url, headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"})
    except httpx.HTTPError as exc:
        raise RetryableError(f"provider did not answer ({type(exc).__name__})") from exc
    if reply.status_code >= 500:
        raise RetryableError(f"provider error {reply.status_code}")
    if reply.status_code != 200:
        raise ProviderError("userinfo_failed", reply.status_code)
    return _json(reply)


def _json(reply: httpx.Response) -> dict[str, Any]:
    try:
        body = reply.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def token_set(body: dict[str, Any]) -> TokenSet:
    access = body.get("access_token")
    if not access:
        raise ProviderError("invalid_response", 200, "the token answer carried no access token")
    try:
        expires = int(body.get("expires_in") or 3600)
    except (TypeError, ValueError):
        expires = 3600
    return TokenSet(access_token=str(access), refresh_token=body.get("refresh_token") or None, expires_in=expires,
                    scope=str(body.get("scope") or ""), token_type=str(body.get("token_type") or "Bearer"),
                    raw=body)
