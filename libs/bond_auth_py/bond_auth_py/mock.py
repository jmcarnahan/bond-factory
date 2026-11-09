"""The mock tier: registered tokens, the ``mock:<email>`` literal and an in-memory identity store.

Used by the verifier while the mock tier is in force and by ``MockIdentityAdmin``. Tests flip ``fail_mail``,
``fail_link`` and ``unavailable`` to force error paths and read ``calls`` to see what the code did.
"""

import json
import threading
import time
from datetime import UTC, datetime

from bond_auth_py.errors import AuthUnavailable, IdentityExists, IdentityNotFound, MailNotSent, TokenError

MOCK_PREFIX = "mock:"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def provider_claims(claim) -> dict:
    """``{sign_in_provider, identities}`` from a token's ``firebase`` claim, with safe defaults."""
    claim = claim if isinstance(claim, dict) else {}
    provider = claim.get("sign_in_provider")
    raw = claim.get("identities")
    identities = ({str(k): [str(v) for v in vals] for k, vals in raw.items() if isinstance(vals, list)}
                  if isinstance(raw, dict) else {})
    return {"sign_in_provider": provider if isinstance(provider, str) and provider else "password",
            "identities": identities}


class MockIdentities:
    """What the mock knows: tokens (``token -> claims``) and identities (``lower(email) -> record``)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.tokens: dict[str, dict] = {}
            self.by_email: dict[str, dict] = {}
            self.calls: list[tuple] = []
            self.sent_mails: list[tuple[str, str]] = []
            self.fail_mail = False
            self.fail_link = False
            self.unavailable = False
            self._n = 0

    # -- tokens --------------------------------------------------------------------------------------------------------
    def register_mock_token(self, token: str, uid: str, email: str, name: str | None = None, *,
                            expired: bool = False, auth_time: float | None = None, provider: str = "password",
                            identities: dict | None = None) -> None:
        """Teach the mock a token. ``auth_time`` is epoch seconds of the last sign-in (default: now)."""
        self.tokens[token] = {"uid": uid, "email": email, "name": name, "expired": expired,
                              "auth_time": auth_time, "provider": provider, "identities": identities or {}}

    def verify(self, token: str) -> dict:
        """Claims for a registered token or the literal ``mock:<email>``; ``TokenError`` otherwise."""
        entry = self.tokens.get(token)
        if entry is None and token.startswith(MOCK_PREFIX) and "@" in token:
            email = token[len(MOCK_PREFIX):].strip().lower()
            known = self.get(email)
            entry = {"uid": known["uid"] if known else "mock-" + email, "email": email, "name": None,
                     "expired": False, "provider": "password", "identities": {}}
        if entry is None:
            raise TokenError("invalid")
        if entry.get("expired"):
            raise TokenError("expired")
        known = self.get(entry["email"])
        if known is not None and known["uid"] == entry["uid"] and known["disabled"]:
            raise TokenError("invalid")  # a disabled user cannot sign in (the real check raises the same way)
        return {"uid": entry["uid"], "email": entry["email"], "name": entry.get("name"),
                "auth_time": entry.get("auth_time") or time.time(),
                **provider_claims({"sign_in_provider": entry.get("provider"), "identities": entry.get("identities")})}

    def load_file(self, path: str) -> int:
        """Load identities from a JSON list ``[{"email", "name"?, "uid"?, "token"?, "providers"?}]``.

        An entry with a ``token`` also registers that token. Returns the number of entries loaded."""
        with open(path, encoding="utf-8") as handle:
            rows = json.load(handle)
        if not isinstance(rows, list):
            raise TypeError("the mock identities file must be a JSON list")
        for row in rows:
            email = str(row["email"]).strip().lower()
            uid = row.get("uid") or self.seed(email, row.get("name"))
            if row.get("uid"):
                self.add_identity(uid, email, providers=row.get("providers") or ["password"], name=row.get("name"))
            if row.get("token"):
                self.register_mock_token(row["token"], uid, email, row.get("name"))
        return len(rows)

    # -- identities ----------------------------------------------------------------------------------------------------
    def seed(self, email: str, name: str | None = None) -> str:
        """Put an identity in the store without going through the code under test. Returns its uid."""
        with self._lock:
            return self._add(email.strip().lower(), name)["uid"]

    def add_identity(self, uid: str, email: str, *, providers: list[str], created_at: datetime | None = None,
                     name: str | None = None) -> None:
        """Put an identity with a chosen uid, providers and creation time (naive UTC; default now)."""
        with self._lock:
            email = email.strip().lower()
            self.by_email[email] = {"uid": uid, "email": email, "name": name, "disabled": False,
                                    "revoked_at": None, "providers": list(providers),
                                    "created_at": created_at or _now()}

    def get(self, email: str) -> dict | None:
        return self.by_email.get((email or "").strip().lower())

    def by_uid(self, uid: str) -> dict | None:
        return next((v for v in self.by_email.values() if v["uid"] == uid), None)

    def _add(self, email: str, name: str | None) -> dict:
        self._n += 1
        entry = {"uid": f"mock-uid-{self._n}", "email": email, "name": name, "disabled": False,
                 "revoked_at": None, "providers": ["password"], "created_at": _now()}
        self.by_email[email] = entry
        return entry

    def _check(self, what: str, *args) -> None:
        self.calls.append((what, *args))
        if self.unavailable:
            raise AuthUnavailable("mock: unavailable")

    def _entry(self, uid: str) -> dict:
        entry = self.by_uid(uid)
        if entry is None:
            raise IdentityNotFound(uid)
        return entry

    # -- the admin operations ------------------------------------------------------------------------------------------
    def create(self, email: str, name: str | None) -> str:
        with self._lock:
            self._check("create", email)
            if email in self.by_email:
                raise IdentityExists(email)
            return self._add(email, name)["uid"]

    def lookup(self, *, email: str | None = None, uid: str | None = None) -> dict | None:
        with self._lock:
            self._check("lookup", email or uid)
            entry = self.get(email) if email else self.by_uid(uid or "")
            if entry is None:
                return None
            return {"uid": entry["uid"], "email": entry["email"], "disabled": entry["disabled"],
                    "providers": list(entry["providers"]), "created_at": entry["created_at"]}

    def set_disabled(self, uid: str, disabled: bool) -> None:
        with self._lock:
            self._check("disable" if disabled else "enable", uid)
            entry = self._entry(uid)
            entry["disabled"] = disabled
            if disabled:
                entry["revoked_at"] = datetime.now(UTC)

    def revoke(self, uid: str) -> None:
        with self._lock:
            self._check("revoke", uid)
            self._entry(uid)["revoked_at"] = datetime.now(UTC)

    def delete(self, uid: str) -> None:
        with self._lock:
            self._check("delete", uid)
            del self.by_email[self._entry(uid)["email"]]

    def update_email(self, uid: str, email: str) -> None:
        with self._lock:
            self._check("update_email", uid, email)
            entry = self._entry(uid)
            if email != entry["email"] and email in self.by_email:
                raise IdentityExists(email)
            del self.by_email[entry["email"]]
            entry["email"] = email
            self.by_email[email] = entry

    def set_password(self, uid: str, password: str) -> None:
        with self._lock:
            self._check("set_password", uid)
            self._entry(uid)["password"] = password

    def send_mail(self, email: str, language: str) -> None:
        with self._lock:
            self.calls.append(("send_mail", email, language))
            if self.fail_mail or self.unavailable or self.get(email) is None:
                raise MailNotSent("mock: mail not sent")
            self.sent_mails.append((email, language))

    def link(self, email: str) -> str:
        with self._lock:
            self.calls.append(("link", email))
            if self.fail_link or self.unavailable or self.get(email) is None:
                raise AuthUnavailable("mock: no link")
            self._n += 1
            return f"https://mock.invalid/__/auth/action?mode=resetPassword&oobCode=mock-code-{self._n}"


_DEFAULT = MockIdentities()


def default_mock() -> MockIdentities:
    """The process-wide mock the verifier and ``MockIdentityAdmin`` share unless given their own."""
    return _DEFAULT


def register_default_token(*args, **kwargs) -> None:
    _DEFAULT.register_mock_token(*args, **kwargs)
