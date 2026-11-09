"""An offline provider: the consent page is the app's own, ``exchange("mock")`` mints tokens.

The code the consent form posts is ``mock``, or ``mock:<urlsafe base64 of the e-mail>`` with an optional
``;decline=<set id>,<set id>``. The identity is that e-mail (default ``email``); a declined set's scopes (from
``set_scopes``) are left out of the grant, except openid, email and profile. The exchange also returns an UNSIGNED
``id_token`` (``alg: none``), which ``identity_from_token_response`` accepts only because ``unsigned_ids_ok`` is set.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from typing import Any
from urllib.parse import urlencode

from bond_oauth import pkce
from bond_oauth.errors import OAuthError, ProviderError
from bond_oauth.identity import FAKE_ISSUER
from bond_oauth.providers import TokenSet
from bond_oauth.scopes import split_scopes

MOCK_CODE = "mock"
FAKE_TENANT = "00000000-0000-4000-8000-0000000000f1"
_KEEP = {"openid", "email", "profile"}


def mock_code(email: str, decline: Sequence[str] = ()) -> str:
    """The code a consent form posts for ``email`` (and the declined set ids)."""
    code = "mock:" + base64.urlsafe_b64encode(email.encode()).decode().rstrip("=")
    return code + (";decline=" + ",".join(decline) if decline else "")


def _b64(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode()).decode().rstrip("=")


class FakeOAuth:
    unsigned_ids_ok = True

    def __init__(self, consent_base: str, email: str = "demo@example.com", *, client_id: str = "fake-client",
                 kind: str = "google", pinned_tenant: str | None = None,
                 set_scopes: Mapping[str, Sequence[str]] | None = None,
                 clock: Callable[[], float] = time.time) -> None:
        self.consent_base = consent_base
        self.email = email
        self.client_id, self.kind, self.pinned_tenant = client_id, kind, pinned_tenant
        self.set_scopes = {key: list(value) for key, value in (set_scopes or {}).items()}
        self.refresh_calls = 0
        self.revoked: list[str] = []
        self._clock = clock
        self._requested: dict[str, dict[str, Any]] = {}  # PKCE challenge -> scopes, nonce, offline asked for
        self._granted: dict[str, list[str]] = {}  # refresh token -> scopes
        self._emails: dict[str, str] = {}  # access token -> the e-mail it was issued for
        self._fail_with: str | None = None

    def fail_refresh_with(self, error: str | None) -> None:
        """The next refreshes answer with this provider error (``None`` clears it)."""
        self._fail_with = error

    def authorize_url(self, *, state: str, challenge: str, scopes: list[str], redirect_uri: str,
                      offline: bool = True, prompt: str | None = None, nonce: str | None = None,
                      login_hint: str | None = None) -> str:
        self._requested[challenge] = {"scopes": list(scopes), "nonce": nonce, "offline": offline}
        query = {"state": state, **({"hint": login_hint} if login_hint else {})}
        return f"{self.consent_base}?{urlencode(query)}"

    def exchange(self, *, code: str, verifier: str, redirect_uri: str) -> TokenSet:
        asked = self._requested.get(pkce.challenge(verifier))
        email, declined = self._parse(code)
        if asked is None or email is None:
            raise OAuthError("invalid_code", "The sign-in code was not accepted")
        skip = {s for set_id in declined for s in self.set_scopes.get(set_id, ())}
        scopes = [s for s in asked["scopes"] if s not in skip or s in _KEEP]
        # Microsoft hands out a refresh token for ``offline_access``; Google for an offline flow.
        refresh = None
        offline = "offline_access" in scopes if self.kind == "microsoft" else asked["offline"]
        if offline:
            refresh = "fake-refresh-" + secrets.token_hex(8)
            self._granted[refresh] = scopes
        access = "fake-access-" + secrets.token_hex(8)
        self._emails[access] = email
        body = {"access_token": access, "expires_in": 3600, "scope": " ".join(scopes), "token_type": "Bearer",
                "id_token": self._id_token(email, asked["nonce"])}
        if refresh:
            body["refresh_token"] = refresh
        return TokenSet(access_token=access, refresh_token=refresh, expires_in=3600, scope=body["scope"],
                        token_type="Bearer", raw=body)

    def _parse(self, code: str) -> tuple[str | None, list[str]]:
        head, *rest = (code or "").split(";")
        declined = [i for part in rest if part.startswith("decline=") for i in part[8:].split(",") if i]
        if head == MOCK_CODE:
            return self.email, declined
        if not head.startswith(MOCK_CODE + ":"):
            return None, []
        text = head[len(MOCK_CODE) + 1:]
        try:
            email = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4)).decode()
        except ValueError:
            return None, []
        return (email, declined) if email else (None, [])

    def _ids(self, email: str) -> tuple[str, str]:
        digest = hashlib.sha1(email.encode()).hexdigest()  # a fake id, not a security use
        return "fake-" + digest[:12], str(uuid.UUID(digest[:32]))

    def _id_token(self, email: str, nonce: str | None) -> str:
        now = self._clock()
        sub, oid = self._ids(email)
        claims: dict[str, Any] = {"iss": FAKE_ISSUER, "aud": self.client_id, "sub": sub, "email": email,
                                  "email_verified": True, "name": email.split("@")[0], "iat": int(now),
                                  "exp": int(now) + 3600}
        if nonce:
            claims["nonce"] = nonce
        if self.kind == "microsoft":
            claims.update({"tid": self.pinned_tenant or FAKE_TENANT, "oid": oid, "preferred_username": email})
        return f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{_b64(claims)}."  # unsigned: the third segment is empty

    def refresh(self, refresh_token: str, *, scopes: list[str]) -> TokenSet:
        self.refresh_calls += 1
        if self._fail_with:
            raise ProviderError(self._fail_with, 400)
        granted = self._granted.get(refresh_token)
        if granted is None:
            raise ProviderError("invalid_grant", 400)
        wanted = split_scopes(scopes) or granted
        scope = " ".join(s for s in wanted if s in granted)
        body = {"access_token": "fake-access-" + secrets.token_hex(8), "expires_in": 3600, "scope": scope,
                "token_type": "Bearer"}
        return TokenSet(access_token=body["access_token"], refresh_token=None, expires_in=3600, scope=scope,
                        token_type="Bearer", raw=body)

    def revoke(self, token: str) -> None:
        self.revoked.append(token)

    def userinfo(self, access_token: str) -> dict[str, Any]:
        email = self._emails.get(access_token, self.email)
        sub, oid = self._ids(email)
        info: dict[str, Any] = {"email": email, "name": email.split("@")[0], "sub": sub}
        if self.kind == "microsoft":
            info.update({"mail": email, "id": oid})
        return info
