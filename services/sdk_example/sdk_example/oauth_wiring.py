"""REPLACE the names. OAuth providers, the scope policy and the token cipher for the example app.

Fake mode: two `FakeOAuth` providers (`fake-google`, `fake-microsoft`) whose consent page is this app's own
`GET /connections/fake/consent`. Real mode: Google and/or Microsoft, each only when its client id and secret are
set (BOND_GOOGLE_CLIENT_ID/SECRET, BOND_MS_CLIENT_ID/SECRET/TENANT). Real Microsoft sign-in needs BOND_MS_TENANT to
be the tenant's GUID (the lib refuses `common`). Every callback address is built on SDK_EXAMPLE_PUBLIC_BASE and
must be registered at the provider (`<base>/auth/signin/<p>/callback` and `<base>/connections/<p>/callback`).

The same provider objects serve sign-in and the connect flow; WHICH scopes each asks comes from `scope_policy`,
never from a library default.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx
from bond_oauth import FakeOAuth, GoogleOAuth, MicrosoftOAuth, OAuthProvider, TokenCipher
from bond_oauth.fake import FAKE_TENANT
from bond_signin import ScopePolicy

from .scope_policy import FAKE_GOOGLE, FAKE_MICROSOFT, build_policy, set_scopes
from .settings import Settings

CONSENT_PATH = "/connections/fake/consent"
FAKE_CLIENT_ID = "fake-client"
DEFAULT_EMAIL = {FAKE_GOOGLE: "demo.google@example.com", FAKE_MICROSOFT: "demo.microsoft@example.com"}


@dataclass
class OAuthWiring:
    providers: dict[str, OAuthProvider]
    cipher: TokenCipher
    policy: ScopePolicy
    client_ids: dict[str, str] = field(default_factory=dict)  # per provider: the OIDC `aud` a sign-in checks
    pinned_tenants: dict[str, str] = field(default_factory=dict)  # Microsoft sign-in: the one tenant allowed
    fakes: dict[str, FakeOAuth] = field(default_factory=dict)


def build_wiring(settings: Settings, http: httpx.Client | None = None) -> OAuthWiring:
    """Raises RuntimeError at startup when no cipher key is available (real mode without BOND_OAUTH_KEY)."""
    if not settings.oauth_key:
        raise RuntimeError("BOND_OAUTH_KEY must be set in real mode")
    cipher = TokenCipher(settings.oauth_key)
    if settings.mode == "fake":
        policy = build_policy(FAKE_GOOGLE, FAKE_MICROSOFT)
        consent = f"{settings.public_base}{CONSENT_PATH}"  # absolute: the browser may be on another origin
        common = {"client_id": FAKE_CLIENT_ID, "set_scopes": set_scopes(policy)}
        fakes = {
            # `email` is what the code `mock` (no identity picked) stands for; the consent page picks real ones.
            FAKE_GOOGLE: FakeOAuth(consent, email=DEFAULT_EMAIL[FAKE_GOOGLE], kind="google", **common),
            FAKE_MICROSOFT: FakeOAuth(consent, email=DEFAULT_EMAIL[FAKE_MICROSOFT], kind="microsoft",
                                      pinned_tenant=FAKE_TENANT, **common),
        }
        return OAuthWiring(providers=dict(fakes), cipher=cipher, policy=policy, fakes=fakes,
                           client_ids={name: FAKE_CLIENT_ID for name in fakes},
                           pinned_tenants={FAKE_MICROSOFT: FAKE_TENANT})
    env = os.environ.get
    client = http or httpx.Client(timeout=15)
    providers: dict[str, OAuthProvider] = {}
    client_ids: dict[str, str] = {}
    pinned: dict[str, str] = {}
    if env("BOND_GOOGLE_CLIENT_ID") and env("BOND_GOOGLE_CLIENT_SECRET"):
        client_ids["google"] = env("BOND_GOOGLE_CLIENT_ID", "")
        providers["google"] = GoogleOAuth(client_ids["google"], env("BOND_GOOGLE_CLIENT_SECRET", ""), client)
    if env("BOND_MS_CLIENT_ID") and env("BOND_MS_CLIENT_SECRET"):
        tenant = env("BOND_MS_TENANT", "common") or "common"
        client_ids["microsoft"], pinned["microsoft"] = env("BOND_MS_CLIENT_ID", ""), tenant
        providers["microsoft"] = MicrosoftOAuth(client_ids["microsoft"], env("BOND_MS_CLIENT_SECRET", ""),
                                                tenant=tenant, http=client)
    return OAuthWiring(providers=providers, cipher=cipher, policy=build_policy("google", "microsoft"),
                       client_ids=client_ids, pinned_tenants=pinned)


def callback_url(settings: Settings, provider: str) -> str:
    """The connect callback registered at the provider (the sign-in callback is the lib's)."""
    return f"{settings.public_base}/connections/{provider}/callback"
