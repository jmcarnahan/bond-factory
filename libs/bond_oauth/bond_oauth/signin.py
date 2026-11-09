"""Sign-in flow: identify a person with the provider's code flow, store a connection only when one was granted.

``SignInFlow`` is stateless like the connect flow (everything rides in the encrypted ``state``). ``complete`` STORES
NOTHING: it returns who signed in and, when mail or calendar scopes came with a refresh token, a ``PendingConnection``.
The caller decides who the person is (``UserDirectory``), then calls ``store`` for the identified user.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from bond_oauth import pkce
from bond_oauth.cipher import TokenCipher
from bond_oauth.errors import OAuthError, RetryableError
from bond_oauth.guid import ATTEMPT, GUID, HEX64
from bond_oauth.identity import OidcIdentity, identity_from_token_response
from bond_oauth.providers import OAuthProvider
from bond_oauth.scopes import is_identity_only, split_scopes
from bond_oauth.service import PendingConnection, connection_fields, store_connection, utcnow
from bond_oauth.state import decode_state, encode_state


@dataclass(frozen=True)
class StartedSignIn:
    url: str = field(repr=False)  # the provider's consent URL (it carries the state)
    nonce: str = field(repr=False)  # bind it to the starting browser (cookie); pass it back as ``expected_nonce``
    state: str = field(repr=False)


@dataclass(frozen=True)
class SignInResult:
    identity: OidcIdentity
    # None for an identity-only grant or when no refresh token came back; repr hidden (sealed tokens inside)
    pending: PendingConnection | None = field(repr=False)
    granted_scopes: list[str]
    redirect_to: str
    attempt_id: str | None
    native: bool
    set_id: str | None


@dataclass(frozen=True)
class StateInfo:
    """What a sign-in state says about itself (``SignInFlow.peek``); no secrets (no verifier)."""
    redirect_to: str
    attempt_id: str | None
    native: bool
    nonce: str | None = field(repr=False)
    device_hash: str | None = field(repr=False)
    provider: str
    set_id: str | None
    expired: bool = False  # authentic but past its 10 minutes (``peek`` only; ``complete`` raises instead)


class SignInFlow:
    """Structurally the ``IdentityFlow`` of ``bond_signin``. Errors carry a ``code``: ``invalid_state``,
    ``signin_expired``, ``invalid_id_token``, ``tenant_mismatch``, ``invalid_code``, ``unknown_provider``,
    ``invalid_request`` and the provider's own error string."""

    def __init__(self, *, providers: Mapping[str, OAuthProvider], cipher: TokenCipher, client_ids: Mapping[str, str],
                 public_base: str, pinned_tenants: Mapping[str, str] | None = None,
                 clock: Callable[[], float] = time.time) -> None:
        missing = [name for name in providers if not client_ids.get(name)]
        if missing:
            raise ValueError(f"no client id for provider(s): {', '.join(sorted(missing))}")
        self._providers, self._cipher, self._client_ids = dict(providers), cipher, dict(client_ids)
        self._base, self._pinned, self._clock = public_base.rstrip("/"), dict(pinned_tenants or {}), clock
        for name, impl in self._providers.items():  # a Microsoft sign-in without one pinned tenant is refused here
            if "microsoft" in name.lower() and not getattr(impl, "unsigned_ids_ok", False):
                pin = self._pinned.get(name) or getattr(impl, "pinned_tenant", None)
                if not isinstance(pin, str) or not GUID.match(pin):
                    raise ValueError(f"provider {name!r} needs a pinned tenant that is a GUID "
                                     "(not common, organizations or consumers)")

    def callback_url(self, provider: str) -> str:
        return f"{self._base}/auth/signin/{provider}/callback"

    def start(self, *, provider: str, scopes: Sequence[str], redirect_to: str, device_hash: str | None = None,
              attempt_id: str | None = None) -> StartedSignIn:
        """The consent URL and the cookie nonce. ``device_hash`` (sha256 hex of the phone's secret) makes it a
        native sign-in. Google asks offline (``prompt=consent``) only when ``scopes`` go beyond identity; Microsoft
        always sends ``prompt=select_account`` (its refresh token comes from the ``offline_access`` scope)."""
        impl = self._providers.get(provider)
        if impl is None:
            raise OAuthError("unknown_provider", "That provider is not configured")
        if device_hash is not None and not HEX64.fullmatch(device_hash):
            raise OAuthError("invalid_request", "The device hash is not valid")
        if attempt_id is not None and not ATTEMPT.fullmatch(attempt_id):
            raise OAuthError("invalid_request", "The attempt id is not valid")
        verifier, nonce = pkce.new_verifier(), secrets.token_urlsafe(12)
        oidc_nonce = hashlib.sha256(nonce.encode()).hexdigest()
        identity_only = is_identity_only(provider, scopes)
        state = encode_state(self._cipher, sub=None, provider=provider, connection_name=provider, verifier=verifier,
                             redirect_to=redirect_to, native=device_hash is not None, intent="signin",
                             device_hash=device_hash, attempt_id=attempt_id, oidc_nonce=oidc_nonce, nonce=nonce)
        prompt = "select_account" if identity_only or "microsoft" in provider.lower() else "consent"
        url = impl.authorize_url(state=state, challenge=pkce.challenge(verifier), scopes=list(scopes),
                                 redirect_uri=self.callback_url(provider), offline=not identity_only, prompt=prompt,
                                 nonce=oidc_nonce)
        return StartedSignIn(url=url, nonce=nonce, state=state)

    def _payload(self, state: str, *, allow_expired: bool = False):
        expired = False
        try:
            payload = decode_state(self._cipher, state)
        except OAuthError as exc:
            if exc.code != "expired_state":
                raise OAuthError("invalid_state", "The sign-in link is not valid") from exc
            payload, expired = decode_state(self._cipher, state, now=0.0), True
            if payload.intent == "signin" and not allow_expired:
                raise OAuthError("signin_expired", "The sign-in took too long; start again") from exc
        if payload.intent != "signin" or not payload.oidc_nonce:
            raise OAuthError("invalid_state", "The sign-in link is not for signing in")
        return (payload, expired) if allow_expired else payload

    def peek(self, *, state: str) -> StateInfo:
        """Decode a sign-in state without any network call or exchange. Raises ``invalid_state`` for an
        unauthentic state or one that is not a sign-in; an authentic but expired state is returned with
        ``expired=True`` (``complete`` raises ``signin_expired`` for it). The router uses it to name the per-flow cookie (sha256 of
        ``nonce``) and to redirect when the provider answers ``error=access_denied`` with no code."""
        p, expired = self._payload(state, allow_expired=True)
        return StateInfo(redirect_to=p.redirect_to, attempt_id=p.attempt_id, native=p.device_hash is not None,
                         nonce=p.nonce, device_hash=p.device_hash, provider=p.provider, set_id=p.set_id, expired=expired)

    def complete(self, *, state: str, code: str, expected_nonce: str | None,
                 expected_device_hash: str | None) -> SignInResult:
        """Check the state and its binding (web: the cookie nonce; native: the device hash), trade the code, read
        the identity. Stores nothing, on success or refusal."""
        payload = self._payload(state)
        bound = (expected_device_hash, payload.device_hash) if payload.device_hash else (expected_nonce, payload.nonce)
        if not bound[0] or not hmac.compare_digest(bound[0].encode(), bound[1].encode()):
            raise OAuthError("invalid_state", "The sign-in was not started in this browser")
        provider = self._providers.get(payload.provider)
        if provider is None:
            raise OAuthError("unknown_provider", "That provider is not configured")
        if not code:
            raise OAuthError("invalid_code", "The provider sent no code")
        tokens = provider.exchange(code=code, verifier=payload.verifier,
                                   redirect_uri=self.callback_url(payload.provider))
        info = self._userinfo(payload.provider, provider, tokens.access_token)
        identity = identity_from_token_response(
            payload.provider, provider, tokens, expected_nonce=payload.oidc_nonce,
            client_id=self._client_ids[payload.provider], userinfo=info, now=self._clock(),
            pinned_tenant=self._pinned.get(payload.provider))
        granted = split_scopes(tokens.scope)
        pending = None
        if tokens.refresh_token and identity.email and not is_identity_only(payload.provider, granted):
            fields = connection_fields(self._cipher, tokens, email=identity.email, name=identity.name,
                                       stamp=utcnow())
            pending = PendingConnection(owner=None, provider=payload.provider,
                                        connection_name=payload.provider, fields=fields)
        return SignInResult(identity=identity, pending=pending, granted_scopes=granted,
                            redirect_to=payload.redirect_to, attempt_id=payload.attempt_id,
                            native=payload.device_hash is not None, set_id=payload.set_id)

    @staticmethod
    def _userinfo(name: str, provider: Any, access_token: str) -> dict | None:
        """The provider's userinfo / ``/me``. For Google the id_token alone identifies, so a failing call gives None
        and does not fail the sign-in. A real Microsoft provider fails closed instead: ``/me`` carries the guest
        markers (``upn``, ``user_type``) that the id_token lacks, so a sign-in without it is not safe to accept."""
        fetch = getattr(provider, "userinfo", None)
        if fetch is None:
            return None
        try:
            return fetch(access_token)
        except (OAuthError, RetryableError):
            if "microsoft" in name.lower() and not getattr(provider, "unsigned_ids_ok", False):
                raise
            return None

    def store(self, session: Any, connection_model: Any, *, owner: str, result: SignInResult,
              connection_name: str | None = None):
        """Store ``result.pending`` under the identified ``owner`` (the one-live-row rule revokes the previous
        connection of that name). Returns the row, or None when the sign-in carried no connection."""
        if result.pending is None:
            return None
        pending = result.pending
        return store_connection(session, connection_model, owner=owner, provider=pending.provider,
                                connection_name=connection_name or pending.provider, fields=pending.fields,
                                stamp=utcnow())
