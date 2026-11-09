"""``GET /auth/providers``: what sign-in methods this server offers. Public client config only, no secrets.

``firebase`` is ``null`` when unconfigured and in mock mode. Dart's ``FirebaseRuntimeConfig.fromProviders``
returns null unless the platform's block is complete, so a half-configured platform is simply not offered.
"""

from bond_auth_py.settings import AuthSettings, mock_active


def firebase_runtime_config(settings: AuthSettings) -> dict | None:
    """The firebase client object, or ``None`` without a project id."""
    project = settings.firebase_project_id
    if not project:
        return None
    return {
        "project_id": project,
        "auth_domain": settings.firebase_auth_domain or f"{project}.firebaseapp.com",
        "messaging_sender_id": settings.firebase_messaging_sender_id,
        "web": {"api_key": settings.web_api_key, "app_id": settings.firebase_web_app_id},
        "ios": {"api_key": settings.firebase_ios_api_key, "app_id": settings.firebase_ios_app_id,
                "bundle_id": settings.firebase_ios_bundle_id},
    }


def providers_payload(settings: AuthSettings, *, sync_url: str | None = None, mock: bool | None = None) -> dict:
    """The merged payload. ``mock`` overrides ``mock_active(settings)`` (an example's fake mode)."""
    is_mock = mock_active(settings) if mock is None else mock
    google = settings.google_enabled
    return {
        "demo": settings.demo_enabled,
        "email_password": settings.email_password_enabled,
        "google": google,
        "google_web_client_id": (settings.google_web_client_id or None) if google else None,
        "apple": settings.apple_enabled,
        "mock": is_mock,
        "firebase": None if is_mock else firebase_runtime_config(settings),
        "sync": {"url": sync_url},
    }
