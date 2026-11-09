"""Auth configuration as one explicit dataclass. Nothing here reads the environment except ``from_env``."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

Tier = Literal["injected", "mock", "firebase"]
_TRUE = {"1", "true", "yes", "on"}


def _flag(env: Mapping[str, str], name: str, default: bool = False) -> bool:
    raw = (env.get(name) or "").strip().lower()
    return default if raw == "" else raw in _TRUE


def _text(env: Mapping[str, str], *names: str) -> str | None:
    for name in names:
        value = (env.get(name) or "").strip()
        if value:
            return value
    return None


@dataclass(frozen=True)
class AuthSettings:
    jwt_secret: str = field(default="", repr=False)
    issuer: str = "bond"
    audience: str = "bond-api"
    access_ttl_minutes: int = 10080
    auth_time_skew_seconds: int = 5
    #: ``injected``: only an installed verifier is used. ``mock``: the mock, if allowed (see ``mock_active``).
    #: ``firebase``: firebase-admin. An installed verifier always wins, whatever the tier.
    tier: Tier = "firebase"
    mock_enabled_only_under_test: bool = True
    #: Second switch for the mock outside pytest (``BOND_AUTH_TEST_ENV``): a test deployment, never a real one.
    test_env: bool = False
    mock_identities_file: str | None = None
    firebase_project_id: str | None = None
    service_account_json: str | None = field(default=None, repr=False)
    service_account_file: str | None = None
    web_api_key: str | None = field(default=None, repr=False)
    app_name: str = "bond"
    google_enabled: bool = False
    google_web_client_id: str | None = None
    apple_enabled: bool = False
    email_password_enabled: bool = True
    demo_enabled: bool = False
    # Public client config served by /auth/providers.
    firebase_auth_domain: str | None = None
    firebase_messaging_sender_id: str | None = None
    firebase_web_app_id: str | None = None
    firebase_ios_api_key: str | None = None
    firebase_ios_app_id: str | None = None
    firebase_ios_bundle_id: str | None = None

    @classmethod
    def from_env(cls, prefix: str = "BOND_AUTH_", firebase_prefix: str = "FIREBASE_",
                 env: Mapping[str, str] | None = None, **overrides) -> "AuthSettings":
        """Read ``<prefix>*`` and ``<firebase_prefix>*`` variables; ``overrides`` win (e.g. ``app_name``).

        JWT: ``<prefix>JWT_SECRET`` (else ``JWT_SECRET_KEY``), ``<prefix>ISSUER``, ``<prefix>AUDIENCE``,
        ``<prefix>ACCESS_TTL_MINUTES`` (else ``ACCESS_TOKEN_EXPIRE_MINUTES``), ``<prefix>AUTH_TIME_SKEW_SECONDS``.
        Mock: ``<prefix>MOCK``, ``<prefix>TEST_ENV``, ``<prefix>MOCK_IDENTITIES_FILE``.
        Flags: ``<prefix>GOOGLE``, ``<prefix>GOOGLE_WEB_CLIENT_ID``, ``<prefix>APPLE``, ``<prefix>EMAIL_PASSWORD``
        (default on), ``<prefix>DEMO``. Firebase: ``<firebase_prefix>`` + ``PROJECT_ID``, ``SERVICE_ACCOUNT_JSON``,
        ``SERVICE_ACCOUNT_FILE``, ``WEB_API_KEY``, ``AUTH_DOMAIN``, ``MESSAGING_SENDER_ID``, ``WEB_APP_ID``,
        ``IOS_API_KEY``, ``IOS_APP_ID``, ``IOS_BUNDLE_ID``.
        """
        env = os.environ if env is None else env

        def own(name: str) -> str | None:
            return _text(env, prefix + name)

        def fb(name: str) -> str | None:
            return _text(env, firebase_prefix + name)

        ttl = own("ACCESS_TTL_MINUTES") or _text(env, "ACCESS_TOKEN_EXPIRE_MINUTES")
        skew = own("AUTH_TIME_SKEW_SECONDS")
        values = {
            "jwt_secret": own("JWT_SECRET") or _text(env, "JWT_SECRET_KEY") or "",
            "tier": "mock" if _flag(env, prefix + "MOCK") else "firebase",
            "test_env": _flag(env, prefix + "TEST_ENV"),
            "mock_identities_file": own("MOCK_IDENTITIES_FILE"),
            "google_enabled": _flag(env, prefix + "GOOGLE"),
            "google_web_client_id": own("GOOGLE_WEB_CLIENT_ID"),
            "apple_enabled": _flag(env, prefix + "APPLE"),
            "email_password_enabled": _flag(env, prefix + "EMAIL_PASSWORD", True),
            "demo_enabled": _flag(env, prefix + "DEMO"),
            "firebase_project_id": fb("PROJECT_ID"),
            "service_account_json": fb("SERVICE_ACCOUNT_JSON"),
            "service_account_file": fb("SERVICE_ACCOUNT_FILE"),
            "web_api_key": fb("WEB_API_KEY"),
            "firebase_auth_domain": fb("AUTH_DOMAIN"),
            "firebase_messaging_sender_id": fb("MESSAGING_SENDER_ID"),
            "firebase_web_app_id": fb("WEB_APP_ID"),
            "firebase_ios_api_key": fb("IOS_API_KEY"),
            "firebase_ios_app_id": fb("IOS_APP_ID"),
            "firebase_ios_bundle_id": fb("IOS_BUNDLE_ID"),
        }
        for key, name in (("issuer", "ISSUER"), ("audience", "AUDIENCE")):
            if own(name):
                values[key] = own(name)
        if ttl:
            values["access_ttl_minutes"] = int(ttl)
        if skew:
            values["auth_time_skew_seconds"] = int(skew)
        values.update(overrides)
        return cls(**values)

    @property
    def firebase_login_enabled(self) -> bool:
        """True when ``/auth/firebase`` can verify tokens: a project id, or the mock tier is in force."""
        return bool(self.firebase_project_id) or mock_active(self)


def under_test(settings: AuthSettings) -> bool:
    """pytest is running, or the explicit test-environment flag is on."""
    return bool(os.environ.get("PYTEST_CURRENT_TEST")) or settings.test_env


def mock_active(settings: AuthSettings) -> bool:
    """The mock verifier is in force: requested (``tier == "mock"``) and allowed here."""
    if settings.tier != "mock":
        return False
    return under_test(settings) or not settings.mock_enabled_only_under_test


def assert_startup_safe(settings: AuthSettings) -> None:
    """Refuse to start with an empty JWT secret, or when the mock is requested where it is not allowed (a token
    that is only an e-mail address is not authentication). Call it from the app's startup."""
    if not (settings.jwt_secret or "").strip():
        raise RuntimeError("The JWT secret is empty. Set it (BOND_AUTH_JWT_SECRET or JWT_SECRET_KEY).")
    if settings.tier == "mock" and not mock_active(settings):
        raise RuntimeError(
            "The mock auth tier is on but this is not a test run. Unset the mock flag, or set the test-environment "
            "flag for a deliberate test deployment."
        )
