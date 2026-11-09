"""User-lifecycle calls against the identity provider, behind a Protocol so tests and mock mode never reach it.

``FirebaseIdentityAdmin`` needs a service-account key (``AuthUnavailable`` otherwise). ``MockIdentityAdmin`` is the
in-memory twin. No error message carries a key, token or e-mail address: log lines name the step and error type only.
"""

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from typing import Protocol

from bond_auth_py.errors import AuthUnavailable, IdentityExists, IdentityNotFound, MailNotSent
from bond_auth_py.firebase_app import admin_app, require_firebase_admin
from bond_auth_py.mock import MockIdentities, default_mock
from bond_auth_py.settings import AuthSettings

LOGGER = logging.getLogger(__name__)


def _fb_auth():
    """``firebase_admin.auth``, imported on use; ``AuthNotConfigured`` when the ``firebase`` extra is missing."""
    require_firebase_admin()
    from firebase_admin import auth

    return auth


#: Identity Toolkit endpoint that sends the "set your password" mail. The web API key rides in the query string,
#: so the URL is never logged and never put in an exception message.
SEND_OOB_URL = "https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode"
MAIL_TIMEOUT_SECONDS = 10.0
_LOCALE = re.compile(r"^[a-z]{2}(-[A-Za-z]{2,4})?$")


class IdentityAdmin(Protocol):
    def get_user(self, *, email: str | None = None, uid: str | None = None) -> dict | None:
        """``{uid, email, disabled, providers, created_at (naive UTC)}`` or ``None``."""

    def create_user(self, email: str, name: str | None = None) -> str: ...

    def set_password(self, uid: str, password: str) -> None: ...

    def disable_user(self, uid: str, disabled: bool = True) -> None: ...

    def delete_user(self, uid: str) -> None: ...

    def revoke_sessions(self, uid: str) -> None: ...

    def update_email(self, uid: str, email: str) -> None: ...

    def send_password_reset(self, email: str, language: str = "en") -> None: ...

    def password_reset_link(self, email: str) -> str: ...


def _norm(email: str) -> str:
    return (email or "").strip().lower()


def _post_json(url: str, body: dict, headers: dict, timeout: float) -> int:
    """POST JSON, return the HTTP status. Network failures raise ``OSError`` (``urllib.error.URLError`` is one)."""
    request = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


class MockIdentityAdmin:
    """In-memory admin over a ``MockIdentities`` store (default: the shared one)."""

    def __init__(self, mock: MockIdentities | None = None):
        self.mock = mock or default_mock()

    def get_user(self, *, email=None, uid=None):
        return self.mock.lookup(email=_norm(email) if email else None, uid=uid)

    def create_user(self, email, name=None):
        return self.mock.create(_norm(email), name)

    def set_password(self, uid, password):
        self.mock.set_password(uid, password)

    def disable_user(self, uid, disabled=True):
        self.mock.set_disabled(uid, disabled)

    def delete_user(self, uid):
        self.mock.delete(uid)

    def revoke_sessions(self, uid):
        self.mock.revoke(uid)

    def update_email(self, uid, email):
        self.mock.update_email(uid, _norm(email))

    def send_password_reset(self, email, language="en"):
        self.mock.send_mail(_norm(email), language if _LOCALE.match(language or "") else "en")

    def password_reset_link(self, email):
        return self.mock.link(_norm(email))


class FirebaseIdentityAdmin:
    """firebase-admin (imported lazily) under the app named ``settings.app_name``."""

    def __init__(self, settings: AuthSettings):
        self.settings = settings

    def _app(self):
        return admin_app(self.settings)

    @staticmethod
    def _fail(exc: Exception, what: str) -> AuthUnavailable:
        LOGGER.warning("firebase %s failed: %s", what, type(exc).__name__)  # type only: messages can echo e-mails
        return AuthUnavailable(f"{what} failed")

    def get_user(self, *, email=None, uid=None):
        fb_auth = _fb_auth()

        try:
            user = (fb_auth.get_user_by_email(_norm(email), app=self._app()) if email
                    else fb_auth.get_user(uid, app=self._app()))
        except fb_auth.UserNotFoundError:
            return None
        except AuthUnavailable:
            raise
        except Exception as exc:
            raise self._fail(exc, "look up user") from exc
        millis = getattr(getattr(user, "user_metadata", None), "creation_timestamp", None)
        created = datetime.fromtimestamp(millis / 1000, UTC).replace(tzinfo=None) if millis else None
        return {"uid": user.uid, "email": _norm(user.email or email or ""), "disabled": bool(user.disabled),
                "providers": [p.provider_id for p in (user.provider_data or [])], "created_at": created}

    def create_user(self, email, name=None):
        fb_auth = _fb_auth()

        email = _norm(email)
        try:
            return fb_auth.create_user(email=email, email_verified=True, display_name=name or None,
                                       app=self._app()).uid
        except fb_auth.EmailAlreadyExistsError as exc:
            raise IdentityExists(email) from exc
        except AuthUnavailable:
            raise
        except Exception as exc:
            raise self._fail(exc, "create user") from exc

    def _update(self, uid: str, what: str, **fields) -> None:
        fb_auth = _fb_auth()

        try:
            fb_auth.update_user(uid, app=self._app(), **fields)
        except fb_auth.UserNotFoundError as exc:
            raise IdentityNotFound(uid) from exc
        except fb_auth.EmailAlreadyExistsError as exc:
            raise IdentityExists(fields.get("email", "")) from exc
        except AuthUnavailable:
            raise
        except Exception as exc:
            raise self._fail(exc, what) from exc

    def set_password(self, uid, password):
        self._update(uid, "set password", password=password)

    def disable_user(self, uid, disabled=True):
        self._update(uid, "disable user" if disabled else "enable user", disabled=disabled)

    def update_email(self, uid, email):
        self._update(uid, "change e-mail", email=_norm(email), email_verified=True)

    def revoke_sessions(self, uid):
        fb_auth = _fb_auth()

        try:
            fb_auth.revoke_refresh_tokens(uid, app=self._app())
        except fb_auth.UserNotFoundError as exc:
            raise IdentityNotFound(uid) from exc
        except AuthUnavailable:
            raise
        except Exception as exc:
            raise self._fail(exc, "revoke sessions") from exc

    def delete_user(self, uid):
        fb_auth = _fb_auth()

        try:
            fb_auth.delete_user(uid, app=self._app())
        except fb_auth.UserNotFoundError as exc:
            raise IdentityNotFound(uid) from exc
        except AuthUnavailable:
            raise
        except Exception as exc:
            raise self._fail(exc, "delete user") from exc

    def send_password_reset(self, email, language="en"):
        """Have Firebase mail the "set your password" link, in the person's language (unknown codes: English)."""
        key = self.settings.web_api_key
        if not key:
            raise MailNotSent("the web API key is not set")
        language = language if _LOCALE.match(language or "") else "en"
        url = SEND_OOB_URL + "?" + urllib.parse.urlencode({"key": key})
        try:
            status = _post_json(url, {"requestType": "PASSWORD_RESET", "email": _norm(email)},
                                {"X-Firebase-Locale": language}, MAIL_TIMEOUT_SECONDS)
        except OSError as exc:
            # The exception text can contain the full URL (with the key): log and raise the type only.
            LOGGER.warning("sendOobCode failed: %s", type(exc).__name__)
            raise MailNotSent("the mail request failed") from None
        if status != 200:
            LOGGER.warning("sendOobCode refused: HTTP %s", status)
            raise MailNotSent(f"Firebase refused the mail (HTTP {status})")

    def password_reset_link(self, email):
        """A one-time link for the admin to hand over when mail cannot be sent. Treat it as a secret."""
        fb_auth = _fb_auth()

        try:
            return fb_auth.generate_password_reset_link(_norm(email), app=self._app())
        except AuthUnavailable:
            raise
        except Exception as exc:
            raise self._fail(exc, "create password link") from exc
