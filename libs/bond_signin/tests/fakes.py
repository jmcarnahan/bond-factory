"""In-memory fakes of the four Protocols. No sibling lib is imported."""

from __future__ import annotations

import hashlib
import itertools
import secrets
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from bond_signin import IdentityTaken, IssuedSession, SessionSpec


class Coded(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class User:
    id: str
    email: str
    name: str = "Person"
    is_active: bool = True
    identity: tuple[str, str] | None = None
    sessions_valid_after: datetime | None = None
    caps: list[str] = field(default_factory=lambda: ["connections.manage"])
    suspended: bool = False
    blocked_provider: str | None = None
    taken_by_other: bool = False
    alive: bool | None = None


class FakeDb:
    """The ``session`` handed to every method: counts commits and rollbacks."""

    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    @contextmanager
    def scope(self, request=None):
        try:
            yield self
        except BaseException:
            self.rollbacks += 1
            raise
        else:
            self.commits += 1


class FakeDirectory:
    def __init__(self) -> None:
        self.by_id = {u.id: u for u in (User("u-alice", "alice@example.com", "Alice"),
                                        User("u-bob", "bob@example.com", "Bob"),
                                        User("u-carol", "carol@example.com", "Carol", is_active=False))}
        self.by_email = {u.email: u for u in self.by_id.values()}
        self.links: list[tuple[str, str, str]] = []
        self.signins: list[dict] = []
        self.refusals: list[dict] = []
        self.invalidated: list[tuple[str, datetime]] = []
        self.invite_calls: list[list[str]] = []
        self.invite_subjects: list[str | None] = []

    def find_by_identity(self, session, provider, subject):
        return next((u for u in self.by_id.values() if u.identity == (provider, subject)), None)

    def find_by_id(self, session, user_id):
        return self.by_id.get(user_id)

    def find_invite(self, session, emails, provider, *, subject=None):
        self.invite_calls.append(list(emails))
        self.invite_subjects.append(subject)
        found = {self.by_email[e].id: self.by_email[e] for e in emails if e in self.by_email}
        return next(iter(found.values())) if len(found) == 1 else None

    def link_identity(self, session, user, provider, subject):
        if user.taken_by_other:
            raise IdentityTaken()
        user.identity = (provider, subject)
        self.links.append((user.id, provider, subject))

    def check_allowed(self, session, user, provider):
        if user.suspended:
            raise Coded("company_suspended")
        if user.blocked_provider == provider:
            raise Coded("provider_not_allowed")

    def capabilities(self, session, user):
        return list(user.caps)

    def session_spec(self, session, user):
        return SessionSpec(sub=user.id, name=user.name, capabilities=list(user.caps), extra_claims={})

    def public(self, session, user):
        return {"id": user.id, "email": user.email, "name": user.name, "capabilities": list(user.caps)}

    def record_sign_in(self, session, user, *, provider, ip, first):
        self.signins.append({"user": user.id, "provider": provider, "ip": ip, "first": first})

    def record_refusal(self, session, reason, *, email, user, provider, ip):
        self.refusals.append({"reason": reason, "email": email, "user": user.id if user else None,
                              "provider": provider, "ip": ip})

    def mark_sessions_invalid(self, session, user, at):
        user.sessions_valid_after = at
        self.invalidated.append((user.id, at))

    def provider_alive(self, session, user, provider):
        return user.alive


class FakeFlow:
    """``complete`` reads the identity from ``code`` (``alice`` -> alice@example.com) unless ``identities`` says."""

    def __init__(self) -> None:
        self.states: dict[str, SimpleNamespace] = {}
        self.stored: list[dict] = []
        self.started: list[dict] = []
        self.completed: list[dict] = []
        self.identities: dict[str, dict] = {}
        self.fail_complete: str | None = None
        self.fail_start: str | None = None
        self.counter = itertools.count(1)

    def identity(self, code: str, provider: str):
        base = {"provider": provider, "subject": f"sub-{code}", "tenant": None, "email": f"{code}@example.com",
                "email_verified": True, "name": code.title(), "auth_time": 1_800_000_000.0}
        return SimpleNamespace(**{**base, **self.identities.get(code, {})})

    def start(self, *, provider, scopes, redirect_to, device_hash=None, attempt_id=None):
        if self.fail_start:
            raise Coded(self.fail_start)
        state = f"state-{next(self.counter)}"
        nonce = secrets.token_hex(16)
        self.states[state] = SimpleNamespace(
            redirect_to=redirect_to, attempt_id=attempt_id, native=device_hash is not None, nonce=nonce,
            device_hash=device_hash, provider=provider, scopes=list(scopes), expired=False)
        self.started.append({"provider": provider, "scopes": list(scopes), "redirect_to": redirect_to,
                             "device_hash": device_hash, "attempt_id": attempt_id})
        return SimpleNamespace(url=f"https://idp.example/authorize?state={state}", nonce=nonce)

    def peek(self, *, state):
        if state not in self.states:
            raise Coded("invalid_state")
        return self.states[state]

    def complete(self, *, state, code, expected_nonce, expected_device_hash):
        self.completed.append({"state": state, "nonce": expected_nonce, "device": expected_device_hash})
        info = self.peek(state=state)
        if self.fail_complete:
            raise Coded(self.fail_complete)
        if not info.native and expected_nonce != info.nonce:
            raise Coded("invalid_state")
        if info.native and expected_device_hash != info.device_hash:
            raise Coded("invalid_state")
        offline = len(info.scopes) > 3
        return SimpleNamespace(identity=self.identity(code, info.provider), pending="PENDING" if offline else None,
                               granted_scopes=info.scopes, redirect_to=info.redirect_to,
                               attempt_id=info.attempt_id, native=info.native)

    def store(self, session, connection_model, *, owner, result, connection_name=None):
        self.stored.append({"owner": owner, "model": connection_model, "pending": result.pending})


class FakeHandoffs:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}
        self.issued: list[dict] = []

    def issue(self, session, *, purpose, provider, payload, device_hash, attempt_id, ttl=120, now=None):
        code = secrets.token_urlsafe(24)
        self.rows[code] = {"purpose": purpose, "payload": payload, "device_hash": device_hash, "used": False,
                           "expires": (time.time() if now is None else now) + ttl}
        self.issued.append({"code": code, "purpose": purpose, "provider": provider, "payload": payload,
                            "attempt_id": attempt_id})
        return code

    def redeem(self, session, *, code, device_secret, purpose, now=None):
        row = self.rows.get(code)
        if row is None or row["used"] or row["purpose"] != purpose or (time.time() if now is None else now) > row["expires"]:
            raise Coded("invalid_handoff")
        row["used"] = True  # burned even when the secret is wrong
        if hashlib.sha256(device_secret.encode()).hexdigest() != row["device_hash"]:
            raise Coded("invalid_handoff")
        return row["payload"]


class FakeSessions:
    def __init__(self) -> None:
        self.tokens: dict[str, dict] = {}
        self.issued: list[dict] = []
        self.rotations: list[dict] = []
        self.revoked_tokens: list[str] = []
        self.revoked_users: list[dict] = []
        self.rotate_error: str | None = None
        self.revoke_error: Exception | None = None
        self.probe_results: list = []
        self.counter = itertools.count(1)

    def _mint(self, user_id: str, provider: str) -> IssuedSession:
        n = next(self.counter)
        token = f"rt-{n}"
        self.tokens[token] = {"user_id": user_id, "provider": provider, "used": False}
        return IssuedSession(access_jwt=f"jwt-{user_id}-{n}", refresh_token=token, family_id=f"fam-{n}",
                             expires_in=3600, user_id=user_id)

    def issue(self, session, *, user_id, auth_time, provider, spec, device_label=None, now=None):
        self.issued.append({"user_id": user_id, "auth_time": auth_time, "provider": provider, "spec": spec,
                            "device_label": device_label})
        return self._mint(user_id, provider)

    def rotate(self, session, *, refresh_token, rotation_id, loader, revocation, probe=None, now=None):
        self.rotations.append({"token": refresh_token, "rotation_id": rotation_id})
        if self.rotate_error:
            raise Coded(self.rotate_error)
        row = self.tokens.get(refresh_token)
        if row is None or row["used"]:
            raise Coded("refresh_reused" if row else "refresh_revoked")
        spec = loader(row["user_id"])
        if spec is None:
            raise Coded("refresh_revoked")
        if revocation.sessions_valid_after(row["user_id"]) is not None:
            raise Coded("refresh_revoked")
        if probe is not None:
            self.probe_results.append(probe(row["user_id"], row["provider"]))
        row["used"] = True
        return self._mint(row["user_id"], row["provider"])

    def revoke_token(self, session, *, refresh_token, reason="logout"):
        if self.revoke_error:
            raise self.revoke_error
        self.revoked_tokens.append(refresh_token)
        return refresh_token in self.tokens

    def revoke_user(self, session, *, user_id, reason="admin", mark_valid_after=None):
        self.revoked_users.append({"user_id": user_id, "reason": reason})
        if mark_valid_after is not None:
            mark_valid_after(user_id, datetime.now(UTC))
        return 3


def identity_ns(**kw: Any) -> SimpleNamespace:
    base = {"provider": "google", "subject": "sub-x", "tenant": None, "email": "alice@example.com",
            "email_verified": True, "name": "Alice", "auth_time": 1_800_000_000.0}
    return SimpleNamespace(**{**base, **kw})
