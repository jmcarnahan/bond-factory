"""The seams. Structural Protocols only: the sibling libs ship classes of these shapes, the app writes ``UserDirectory``.

Every method says which ``code`` values it may raise. An exception is understood by a ``str`` attribute ``code``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class SessionSpec:
    """What goes into the access token (same field names as the sessions lib)."""

    sub: str
    name: str | None = None
    capabilities: list[str] = field(default_factory=list)
    extra_claims: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IssuedSession:
    """An issued session (same field names as the sessions lib)."""

    access_jwt: str = field(repr=False)
    refresh_token: str = field(repr=False)
    family_id: str
    expires_in: int
    user_id: str = ""


class UserRef(Protocol):
    """Opaque user row. ``identity`` is the bound ``(provider, subject)`` or None."""

    id: str
    is_active: bool
    identity: tuple[str, str] | None
    sessions_valid_after: datetime | None


class OidcIdentity(Protocol):
    """What a completed sign-in yields (``email_verified`` may be a bool or the strings "true"/"false")."""

    provider: str
    subject: str
    tenant: str | None
    email: str
    email_verified: Any
    name: str | None
    auth_time: float | None


class StateInfo(Protocol):
    """A decoded sign-in state, no network. ``device_hash`` is set for native sign-ins."""

    redirect_to: str
    attempt_id: str | None
    native: bool
    nonce: str | None
    device_hash: str | None
    provider: str
    expired: bool


class StartedSignIn(Protocol):
    url: str
    nonce: str


class SignInResult(Protocol):
    identity: OidcIdentity
    pending: Any | None
    granted_scopes: list[str]
    redirect_to: str
    attempt_id: str | None
    native: bool


@runtime_checkable
class IdentityFlow(Protocol):
    """The IdP leg. Stores nothing in ``start``/``complete``; ``store`` writes the connection row."""

    def start(self, *, provider: str, scopes: Sequence[str], redirect_to: str, device_hash: str | None = None,
              attempt_id: str | None = None) -> StartedSignIn:
        """Raises ``invalid_request``."""

    def peek(self, *, state: str) -> StateInfo:
        """Decode a state. Raises ``invalid_state``; an authentic but old state returns ``expired=True``."""

    def complete(self, *, state: str, code: str, expected_nonce: str | None,
                 expected_device_hash: str | None) -> SignInResult:
        """Raises ``invalid_state``, ``signin_expired``, ``invalid_id_token``, ``tenant_mismatch``, ``provider_error``."""

    def store(self, session: Any, connection_model: Any, *, owner: str, result: SignInResult,
              connection_name: str | None = None) -> Any:
        """Write the connection for ``result.pending`` under ``owner``."""


@runtime_checkable
class HandoffStore(Protocol):
    def issue(self, session: Any, *, purpose: str, provider: str, payload: dict, device_hash: str,
              attempt_id: str | None, ttl: int = 120, now: float | None = None) -> str:
        """A one-time code for ``payload``."""

    def redeem(self, session: Any, *, code: str, device_secret: str, purpose: str,
               now: float | None = None) -> dict:
        """Single use. Raises ``invalid_handoff`` (wrong code, secret, purpose; used; expired)."""


@runtime_checkable
class SessionIssuer(Protocol):
    def issue(self, session: Any, *, user_id: str, auth_time: float, provider: str, spec: SessionSpec,
              device_label: str | None = None, now: float | None = None) -> IssuedSession:
        """Mint an access token and a refresh token."""

    def rotate(self, session: Any, *, refresh_token: str, rotation_id: str | None,
               loader: Callable[[str], SessionSpec | None], revocation: Any,
               probe: Callable[[str, str], bool | None] | None = None, now: float | None = None) -> IssuedSession:
        """Raises ``refresh_reused``, ``refresh_expired``, ``refresh_revoked``."""

    def revoke_token(self, session: Any, *, refresh_token: str, reason: str = "logout") -> bool: ...

    def revoke_user(self, session: Any, *, user_id: str, reason: str = "admin",
                    mark_valid_after: Callable[[str, datetime], None] | None = None) -> int:
        """Revokes every live row, then calls ``mark_valid_after(user_id, aware_utc_datetime)``."""


@runtime_checkable
class UserDirectory(Protocol):
    """The one thing an app writes. Methods get the open DB ``session`` of the sign-in transaction."""

    def find_by_identity(self, session: Any, provider: str, subject: str) -> UserRef | None: ...

    def find_by_id(self, session: Any, user_id: str) -> UserRef | None: ...

    def find_invite(self, session: Any, emails: Sequence[str], provider: str, *,
                    subject: str | None = None) -> UserRef | None:
        """Candidates are lowercased and normalised. None means ``not_invited``; two candidates resolving to
        DIFFERENT users must also give None. ``subject`` is the IdP subject of the identity, so an app can also match a
        pre-known subject (for example a backfill from an earlier sign-in system). May create or promote a row
        inside the transaction."""

    def link_identity(self, session: Any, user: UserRef, provider: str, subject: str) -> None:
        """Raises ``identity_mismatch`` when the identity belongs to another user."""

    def check_allowed(self, session: Any, user: UserRef, provider: str) -> None:
        """Raises ``company_suspended`` or ``provider_not_allowed``."""

    def capabilities(self, session: Any, user: UserRef) -> list[str]: ...

    def session_spec(self, session: Any, user: UserRef) -> SessionSpec: ...

    def public(self, session: Any, user: UserRef) -> dict:
        """The ``user`` JSON of every answer, the shape of ``/auth/me``."""

    def record_sign_in(self, session: Any, user: UserRef, *, provider: str, ip: str | None, first: bool) -> None: ...

    def record_refusal(self, session: Any, reason: str, *, email: str | None, user: UserRef | None,
                       provider: str, ip: str | None) -> None: ...

    def mark_sessions_invalid(self, session: Any, user: UserRef, at: datetime) -> None: ...

    def provider_alive(self, session: Any, user: UserRef, provider: str) -> bool | None:
        """False: the IdP account is gone. None: unknown (identity-only apps)."""
