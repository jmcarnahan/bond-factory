"""Named scope sets and drift detection."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

GOOGLE_DEFAULT = (
    "https://www.googleapis.com/auth/gmail.send",
    "openid",
    "email",
    "https://www.googleapis.com/auth/calendar.events",
)
MICROSOFT_BASE = ("Mail.Send", "Mail.Read", "Calendars.ReadWrite", "MailboxSettings.Read", "User.Read",
                  "offline_access")
MICROSOFT_OFFICE = ("Contacts.ReadWrite", "Files.ReadWrite")

GOOGLE_SIGNIN = ("openid", "email", "profile")
MICROSOFT_SIGNIN = ("openid", "profile", "email")
MICROSOFT_SIGNIN_FULL = MICROSOFT_SIGNIN + ("offline_access", "User.Read", "Mail.Send", "Mail.Read",
                                            "Calendars.ReadWrite")
GOOGLE_MAIL_SEND = ("https://www.googleapis.com/auth/gmail.send",)
GOOGLE_CALENDAR = ("https://www.googleapis.com/auth/calendar.events",)

# compared by ``_short`` names, where "email" and "profile" are the aliases of their userinfo forms
_GOOGLE_IDENTITY = frozenset({"openid", "userinfo.email", "userinfo.profile"})
_MICROSOFT_IDENTITY = _GOOGLE_IDENTITY | {"user.read"}
_ALIASES = {"email": "userinfo.email", "profile": "userinfo.profile"}


def split_scopes(value: str | Iterable[str] | None) -> list[str]:
    if not value:
        return []
    return value.split() if isinstance(value, str) else [s for s in value if s]


def _short(scope: str) -> str:
    """Resource-qualified scopes (``https://graph.microsoft.com/Mail.Read``) compare by their last segment."""
    name = scope.rsplit("/", 1)[-1].lower()
    return _ALIASES.get(name, name)


def scope_drift(granted: str | Iterable[str] | None, wanted: str | Iterable[str] | None) -> list[str]:
    """The ``wanted`` scopes missing from ``granted`` (both a space-separated string or a list), sorted."""
    have = {_short(s) for s in split_scopes(granted)}
    return sorted(s for s in split_scopes(wanted) if _short(s) not in have)


def is_identity_only(provider_name: str, scopes: Sequence[str]) -> bool:
    """True when ``scopes`` ask for nothing beyond who the person is: no mail, calendar or long-lived access.

    Google: a subset of openid, email, profile. Microsoft (a provider name containing ``microsoft``): a subset of
    openid, profile, email and User.Read, and never ``offline_access`` (that asks for a refresh token).
    """
    names = [_short(s) for s in split_scopes(list(scopes))]
    allowed = _MICROSOFT_IDENTITY if "microsoft" in provider_name.lower() else _GOOGLE_IDENTITY
    return all(name in allowed for name in names)
