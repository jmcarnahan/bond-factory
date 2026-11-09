"""The firebase-admin app: service-account loading and the lazily created, per-name app.

``firebase_admin`` is imported inside functions only, so importing this library never needs it and tests can
substitute a fake module. With only a project id the app can verify tokens ("verify-only"); with a service-account
key it is "admin-ready" and can also manage users and check token revocation.
"""

import json
import logging
import os
import threading

from bond_auth_py.errors import AuthUnavailable
from bond_auth_py.settings import AuthSettings, mock_active

LOGGER = logging.getLogger(__name__)

_apps: dict[str, object] = {}
_apps_lock = threading.Lock()
_sa_cache: dict = {}


def reset_cache() -> None:
    """Forget the cached apps and parsed keys. Tests only."""
    _apps.clear()
    _sa_cache.clear()


def _load(raw: str | None, path: str | None) -> dict | None:
    if raw:
        try:
            info = json.loads(raw)
        except ValueError:
            LOGGER.warning("The service-account JSON is not valid JSON; ignoring it")
            info = None
        if isinstance(info, dict) and info.get("private_key"):
            return info
        LOGGER.warning("The service-account JSON is not a service-account key; ignoring it")
    if path:
        try:
            with open(path, encoding="utf-8") as handle:
                info = json.load(handle)
        except (OSError, ValueError):
            LOGGER.warning("The service-account file could not be read as JSON; ignoring it")
            return None
        if isinstance(info, dict) and info.get("private_key"):
            return info
        LOGGER.warning("The service-account file is not a service-account key; ignoring it")
    return None


def service_account_info(settings: AuthSettings) -> dict | None:
    """The parsed key: JSON text first, then the file; ``None`` when neither is usable.

    Cached per distinct setting (a file is re-read when its size or mtime changes): it runs on every sign-in."""
    raw, path = settings.service_account_json, settings.service_account_file
    stamp = None
    if path and not raw:
        try:
            stat = os.stat(path)
            stamp = (stat.st_size, stat.st_mtime_ns)
        except OSError:
            stamp = None
    key = (raw, path, stamp)
    if key not in _sa_cache:
        _sa_cache.clear()
        _sa_cache[key] = _load(raw, path)
    return _sa_cache[key]


def admin_ready(settings: AuthSettings) -> bool:
    """True when user-lifecycle calls can run: a usable key is configured, or the mock is in force."""
    return mock_active(settings) or service_account_info(settings) is not None


def check_service_account(settings: AuthSettings) -> None:
    """Startup check: a key that is SET must be usable, else a typo silently makes the API verify-only (no
    revoked-token checks). Raises ``RuntimeError`` and never quotes the key."""
    if not (settings.service_account_json or settings.service_account_file):
        return
    info = service_account_info(settings)
    if info is None:
        raise RuntimeError("The Firebase service-account setting is set but is not a usable key (malformed JSON, "
                           "missing file, or no private_key). Fix it, or unset it to run verify-only.")
    try:
        from firebase_admin import credentials

        credentials.Certificate(info)
    except Exception as exc:  # noqa: BLE001 - any rejection means "not usable"; the type is reported, never the key
        raise RuntimeError(f"The Firebase service-account key is not accepted ({type(exc).__name__}). "
                           "Fix it, or unset it to run verify-only.") from None


def firebase_app(settings: AuthSettings):
    """The firebase-admin app named ``settings.app_name``, initialised once per name."""
    app = _apps.get(settings.app_name)
    if app is not None:
        return app
    with _apps_lock:
        if settings.app_name not in _apps:
            import firebase_admin
            from firebase_admin import credentials

            kwargs = {}
            project = settings.firebase_project_id
            info = service_account_info(settings)
            if info is not None:
                kwargs["credential"] = credentials.Certificate(info)
                project = project or info.get("project_id") or ""
            options = {"projectId": project} if project else {}
            _apps[settings.app_name] = firebase_admin.initialize_app(options=options, name=settings.app_name,
                                                                    **kwargs)
    return _apps[settings.app_name]


def admin_app(settings: AuthSettings):
    """The admin-credentialed app, or ``AuthUnavailable`` (verify-only cannot manage users)."""
    if service_account_info(settings) is None:
        raise AuthUnavailable("firebase admin is not configured")
    try:
        return firebase_app(settings)
    except Exception as exc:
        LOGGER.warning("firebase admin app could not start: %s", type(exc).__name__)
        raise AuthUnavailable("firebase admin could not start") from exc
