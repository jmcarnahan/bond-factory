"""The connection life cycle: start, complete, status, disconnect, access_token.

Datetimes are naive UTC. State expiry uses the real clock (``state.py``); ``now`` here only stamps rows.
Functions that change a row commit it, because ``access_token`` raises right after marking a connection.
"""

from __future__ import annotations

import hmac
import json
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from bond_oauth import pkce
from bond_oauth.cipher import TokenCipher
from bond_oauth.errors import OAuthError, ProviderError, ReconnectRequired, RetryableError
from bond_oauth.providers import OAuthProvider
from bond_oauth.scopes import split_scopes
from bond_oauth.state import decode_state, encode_state

LOGGER = logging.getLogger(__name__)
ACCESS_TTL_SECONDS = 50 * 60
EXPIRY_MARGIN_SECONDS = 120
RECONNECT_CODES = frozenset({"invalid_grant", "unauthorized_client", "invalid_client"})

_monotonic: Callable[[], float] = time.monotonic  # tests replace it to age the cache
_CACHE: dict[str, tuple[str, float, str]] = {}  # connection id -> (access token, expiry, refresh ciphertext)


@dataclass(frozen=True)
class ConnectionStatus:
    connected: bool
    email: str | None = None
    connected_at: datetime | None = None
    needs_reconnect: bool = False
    scopes: list[str] = field(default_factory=list)
    provider: str = ""
    connection_name: str = ""
    last_error: str | None = None


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def forget_access(connection_id: str | None = None) -> None:
    """Drop one cached access token, or all of them."""
    if connection_id is None:
        _CACHE.clear()
    else:
        _CACHE.pop(connection_id, None)


def _owner(model: Any, user_id: str | None):
    return model.user_id.is_(None) if user_id is None else model.user_id == user_id


def _live(session: Session, model: Any, *, user_id: str | None, provider: str, connection_name: str | None):
    stmt = select(model).where(_owner(model, user_id), model.provider == provider, model.revoked_at.is_(None))
    if connection_name is not None:
        stmt = stmt.where(model.connection_name == connection_name)
    return list(session.execute(stmt.order_by(model.connected_at.desc())).scalars())


@dataclass(frozen=True)
class StartedFlow:
    state: str
    authorize_url: str
    nonce: str  # also inside the state; bind it to the starting browser (cookie) and pass it as ``expected_nonce``


def start_flow(session: Session, *, user_id: str, provider_name: str, provider: OAuthProvider, scopes: list[str],
               redirect_to: str, cipher: TokenCipher, redirect_uri: str, shared: bool = False,
               connection_name: str | None = None) -> StartedFlow:
    """The state, the provider's consent URL and the state's nonce. ``redirect_to`` rides inside the encrypted
    state; the app validates it first.

    The state alone does not prove that the browser finishing the flow is the one that started it. Set the nonce as
    an httponly cookie in that browser before sending it to the consent URL and pass the cookie value to
    ``complete(expected_nonce=...)``; otherwise a victim can be tricked into finishing an attacker's flow.
    ``shared=True`` connects a shared mailbox (``user_id`` NULL on the row); who may do that is the app's call.
    """
    verifier = pkce.new_verifier()
    state = encode_state(cipher, sub=user_id, provider=provider_name, connection_name=connection_name or provider_name,
                         verifier=verifier, redirect_to=redirect_to, shared=shared)
    url = provider.authorize_url(state=state, challenge=pkce.challenge(verifier), scopes=list(scopes),
                                 redirect_uri=redirect_uri)
    return StartedFlow(state=state, authorize_url=url, nonce=decode_state(cipher, state).nonce)


def start(session: Session, **kwargs: Any) -> str:
    """``start_flow(...).authorize_url`` (no browser binding: only for callers that bind the state some other way)."""
    return start_flow(session, **kwargs).authorize_url


def complete(session: Session, *, state: str, code: str, providers: Mapping[str, OAuthProvider], cipher: TokenCipher,
             connection_model: Any, redirect_uri: str, expected_nonce: str, expected_user_id: str | None,
             now: datetime | None = None, expected_provider: str | None = None):
    """Verify the state, trade the code, store the connection. Live rows of the same
    (owner, provider, connection_name) are revoked first, so one live row remains. Returns the new row.

    ``expected_nonce`` (the browser-bound cookie value) is REQUIRED and must equal the state's nonce, else
    ``invalid_state``; leaving it out is a ``TypeError``, so a flow can never be completed unbound by accident.
    ``expected_user_id`` is the signed-in user the state must belong to; pass ``None`` only when there is no session.
    A concurrent callback that wins the live-row race (unique index violation) is revoked and the insert is retried
    once; a second violation raises ``OAuthError("conflict")``."""
    stamp = now or utcnow()
    payload = decode_state(cipher, state)
    if not expected_nonce or not hmac.compare_digest(expected_nonce.encode(), payload.nonce.encode()):
        raise OAuthError("invalid_state", "The sign-in was not started in this browser")
    if expected_provider is not None and payload.provider != expected_provider:
        raise OAuthError("provider_mismatch", "The sign-in belongs to another provider")
    if expected_user_id is not None and payload.sub != expected_user_id:
        raise OAuthError("invalid_state", "The sign-in link belongs to someone else")
    provider = providers.get(payload.provider)
    if provider is None:
        raise OAuthError("unknown_provider", "That provider is not configured")
    if not code:
        raise OAuthError("invalid_code", "The provider sent no code")
    tokens = provider.exchange(code=code, verifier=payload.verifier, redirect_uri=redirect_uri)
    if not tokens.refresh_token:
        raise OAuthError("no_refresh_token", "The provider gave no long-lived access; connect again and allow it")
    info = provider.userinfo(tokens.access_token)
    email = str(info.get("email") or "").strip().lower()
    if not email:
        raise OAuthError("no_email", "The provider did not share the account address")
    owner = None if payload.shared else payload.sub
    for attempt in (1, 2):
        for old in _live(session, connection_model, user_id=owner, provider=payload.provider,
                         connection_name=payload.connection_name):
            old.revoked_at, old.updated_at = stamp, stamp
            forget_access(old.id)
        session.flush()  # the revocation must reach the database before the insert
        row = connection_model(
            user_id=owner, provider=payload.provider, connection_name=payload.connection_name, account_email=email,
            scopes=tokens.scope, access_token_enc=cipher.encrypt(tokens.access_token),
            refresh_token_enc=cipher.encrypt(tokens.refresh_token), token_type=tokens.token_type,
            expires_at=stamp + timedelta(seconds=tokens.expires_in), connected_at=stamp, created_at=stamp,
            updated_at=stamp, provider_metadata=json.dumps({"name": info.get("name")}) if info.get("name") else None)
        session.add(row)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            if attempt == 2:
                raise OAuthError("conflict", "Another sign-in finished at the same time; try again") from None
            continue
        return row
    raise AssertionError("unreachable")  # pragma: no cover


def status(session: Session, *, user_id: str | None, provider: str, connection_model: Any,
           connection_name: str | None = None) -> ConnectionStatus:
    """``connected`` = a live row exists; ``needs_reconnect`` = that row carries a ``last_error``."""
    rows = _live(session, connection_model, user_id=user_id, provider=provider, connection_name=connection_name)
    if not rows:
        return ConnectionStatus(connected=False, provider=provider, connection_name=connection_name or provider)
    row = rows[0]
    return ConnectionStatus(connected=True, email=row.account_email, connected_at=row.connected_at,
                            needs_reconnect=bool(row.last_error), scopes=split_scopes(row.scopes),
                            provider=row.provider, connection_name=row.connection_name, last_error=row.last_error)


def disconnect(session: Session, *, user_id: str | None, provider_name: str, connection_model: Any,
               provider: OAuthProvider | None = None, cipher: TokenCipher | None = None,
               connection_name: str | None = None, now: datetime | None = None) -> int:
    """Mark live rows revoked and, best effort, ask the provider to forget the refresh token. Returns the row count."""
    stamp = now or utcnow()
    rows = _live(session, connection_model, user_id=user_id, provider=provider_name, connection_name=connection_name)
    for row in rows:
        row.revoked_at, row.updated_at = stamp, stamp
        forget_access(row.id)
        if provider is not None and cipher is not None:
            try:
                provider.revoke(cipher.decrypt(row.refresh_token_enc))
            except (ValueError, OAuthError, RetryableError, httpx.HTTPError):
                LOGGER.info("oauth: the provider revoke did not go through; the connection is closed here anyway")
    session.commit()
    return len(rows)


def _needs_reconnect(session: Session, connection: Any, reason: str, *, mark: bool,
                     hook: Callable[[Any, str], None] | None, now: datetime) -> ReconnectRequired:
    forget_access(connection.id)
    if mark:
        first = not connection.last_error
        connection.last_error, connection.updated_at = reason[:200], now
        session.commit()
        if first and hook is not None:
            hook(connection, reason)
    return ReconnectRequired(reason)


def access_token(session: Session, connection: Any, *, provider: OAuthProvider, cipher: TokenCipher,
                 mark: bool = True, now: datetime | None = None,
                 on_reconnect_needed: Callable[[Any, str], None] | None = None) -> str:
    """A usable access token (cached 50 minutes in memory per connection and refresh ciphertext).

    A refresh the provider rejects (invalid_grant, unauthorized_client, invalid_client, HTTP 401) raises
    ``ReconnectRequired``; with ``mark`` it also sets ``last_error`` and fires ``on_reconnect_needed`` on the first
    transition only. ``mark=False`` (read paths) never writes the row. Timeouts and 5xx raise ``RetryableError``.
    The refresh asks for the STORED scopes, never the app's current configuration.
    """
    stamp = now or utcnow()
    if connection.revoked_at is not None:
        raise ReconnectRequired("revoked")
    hit = _CACHE.get(connection.id)
    if hit is not None and hit[1] > _monotonic() and hit[2] == connection.refresh_token_enc:
        return hit[0]
    try:
        refresh = cipher.decrypt(connection.refresh_token_enc)
    except ValueError:
        raise _needs_reconnect(session, connection, "undecryptable", mark=mark, hook=on_reconnect_needed,
                               now=stamp) from None
    try:
        tokens = provider.refresh(refresh, scopes=split_scopes(connection.scopes))
    except ProviderError as exc:
        if exc.code in RECONNECT_CODES or exc.status == 401:
            raise _needs_reconnect(session, connection, exc.code, mark=mark, hook=on_reconnect_needed,
                                   now=stamp) from exc
        raise RetryableError(f"token refresh refused ({exc.code})") from exc
    except httpx.HTTPError as exc:
        raise RetryableError(f"provider did not answer ({type(exc).__name__})") from exc
    ttl = min(ACCESS_TTL_SECONDS, tokens.expires_in - EXPIRY_MARGIN_SECONDS)  # never cache past the token's life
    if mark:
        connection.access_token_enc = cipher.encrypt(tokens.access_token)
        if tokens.refresh_token:
            connection.refresh_token_enc = cipher.encrypt(tokens.refresh_token)
    if ttl > 0:
        _CACHE[connection.id] = (tokens.access_token, _monotonic() + ttl, connection.refresh_token_enc)
    if mark:
        connection.expires_at = stamp + timedelta(seconds=tokens.expires_in)
        connection.last_error, connection.updated_at = None, stamp
        session.commit()
    return tokens.access_token
