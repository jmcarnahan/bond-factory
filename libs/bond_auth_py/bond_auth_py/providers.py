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


def providers_payload(settings: AuthSettings, *, sync_url: str | None = None, mock: bool | None = None,
                      signin: list[dict] | None = None, break_glass: bool = False,
                      default_flow: str = "firebase") -> dict:
    """The merged payload. ``mock`` overrides ``mock_active(settings)`` (an example's fake mode).

    ``signin`` lists the direct sign-in providers (only ``id`` and ``label`` are served), ``break_glass`` says the
    Firebase e-mail and password form is on, ``default_flow`` (``signin`` or ``firebase``) is what the client
    shows first. Each of the three keys is present only when it differs from ``[]``, ``False``, ``"firebase"``."""
    is_mock = mock_active(settings) if mock is None else mock
    google = settings.google_enabled
    payload = {
        "demo": settings.demo_enabled,
        "email_password": settings.email_password_enabled,
        "google": google,
        "google_web_client_id": (settings.google_web_client_id or None) if google else None,
        "apple": settings.apple_enabled,
        "mock": is_mock,
        "firebase": None if is_mock else firebase_runtime_config(settings),
        "sync": {"url": sync_url},
    }
    # Added only when set, so an app without direct sign-in serves exactly the old payload; clients default
    # the missing keys to [], false and "firebase".
    if signin:
        payload["signin"] = [{"id": str(p["id"]), "label": str(p["label"])} for p in signin]
    if break_glass:
        payload["break_glass"] = True
    if default_flow != "firebase":
        payload["default_flow"] = default_flow
    return payload
