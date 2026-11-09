"""OAuth providers, scopes and the token cipher for the example app.

Fake mode: two `FakeOAuth` providers (`fake-google`, `fake-microsoft`) whose consent page is this app's own
`GET /connections/fake/consent`. Real mode: Google and/or Microsoft, each only when its client id and secret are
set (BOND_GOOGLE_CLIENT_ID/SECRET, BOND_MS_CLIENT_ID/SECRET/TENANT). BOND_OAUTH_REDIRECT_BASE pins the public
base URL used for the callback (it must match what the provider has registered); without it the request's
own base URL is used.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx
from bond_oauth import (
    GOOGLE_DEFAULT,
    MICROSOFT_BASE,
    FakeOAuth,
    GoogleOAuth,
    MicrosoftOAuth,
    OAuthProvider,
    TokenCipher,
)
from fastapi import Request

from .settings import Settings

CONSENT_PATH = "/connections/fake/consent"
FAKE_GOOGLE, FAKE_MICROSOFT = "fake-google", "fake-microsoft"


@dataclass
class OAuthWiring:
    providers: dict[str, OAuthProvider]
    scopes: dict[str, list[str]]
    cipher: TokenCipher
    fakes: dict[str, FakeOAuth] = field(default_factory=dict)


def build_wiring(settings: Settings, http: httpx.Client | None = None) -> OAuthWiring:
    """Raises RuntimeError at startup when no cipher key is available (real mode without BOND_OAUTH_KEY)."""
    if not settings.oauth_key:
        raise RuntimeError("BOND_OAUTH_KEY must be set in real mode")
    cipher = TokenCipher(settings.oauth_key)
    if settings.mode == "fake":
        fakes = {
            FAKE_GOOGLE: FakeOAuth(CONSENT_PATH, email="demo.google@example.com"),
            FAKE_MICROSOFT: FakeOAuth(CONSENT_PATH, email="demo.microsoft@example.com"),
        }
        scopes = {FAKE_GOOGLE: list(GOOGLE_DEFAULT), FAKE_MICROSOFT: list(MICROSOFT_BASE)}
        return OAuthWiring(providers=dict(fakes), scopes=scopes, cipher=cipher, fakes=fakes)
    env = os.environ.get
    client = http or httpx.Client(timeout=15)
    providers: dict[str, OAuthProvider] = {}
    scopes: dict[str, list[str]] = {}
    if env("BOND_GOOGLE_CLIENT_ID") and env("BOND_GOOGLE_CLIENT_SECRET"):
        providers["google"] = GoogleOAuth(env("BOND_GOOGLE_CLIENT_ID", ""), env("BOND_GOOGLE_CLIENT_SECRET", ""), client)
        scopes["google"] = list(GOOGLE_DEFAULT)
    if env("BOND_MS_CLIENT_ID") and env("BOND_MS_CLIENT_SECRET"):
        providers["microsoft"] = MicrosoftOAuth(env("BOND_MS_CLIENT_ID", ""), env("BOND_MS_CLIENT_SECRET", ""),
                                                tenant=env("BOND_MS_TENANT", "common") or "common", http=client)
        scopes["microsoft"] = list(MICROSOFT_BASE)
    return OAuthWiring(providers=providers, scopes=scopes, cipher=cipher)


def public_base(request: Request) -> str:
    return (os.environ.get("BOND_OAUTH_REDIRECT_BASE") or str(request.base_url)).rstrip("/")


def callback_url(request: Request, provider: str) -> str:
    return f"{public_base(request)}/connections/{provider}/callback"
