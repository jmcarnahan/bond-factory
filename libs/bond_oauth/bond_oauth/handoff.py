"""One-time hand-off of a finished native-app connection.

DEPRECATED in 0.2.0 (removed in 0.3.0): use ``handoff_store.HandoffStore`` (a database table, device-bound, single
use across processes). These functions keep working until the example switches.

A phone app has no browser session, so the callback of a ``native=True`` flow runs without one. It stores NOTHING:
``complete`` returns a ``PendingConnection`` and ``issue_handoff`` seals it (encrypted tokens included) into a
short-lived ``code``. The app, which holds the user's bearer token, redeems the code once, and only then is the row
inserted. Only the user who started the flow can redeem, so a victim lured through an attacker's link gets a code
bound to the attacker, redeems as themself, is refused and nothing is stored; the attacker never sees the code,
because it goes to the victim's app scheme.

LIMIT: single use is enforced by a process-local registry of redeemed nonces. With several server processes (or after
a restart inside the 120 s life of a code) a code could be redeemed again. A replay within the 120 s re-stores the same connection and revokes the live one,
which can undo a disconnect made in between. For a multi-process deployment keep the redeemed nonces in a database
table (unique on the nonce) in the app instead.

The code is bound to the user, not to the device: a custom URL scheme can be claimed by another app on the phone, and
such an app holding a bearer token for the starting user could redeem. Use universal links / app links in production;
a consent screen cannot prevent this.
The code carries the encrypted tokens and can reach about 5 KB with provider-sized tokens (fine for iOS and Android
intents, but long).
"""

from __future__ import annotations

import json
import secrets
import threading
import time
from typing import Any

from sqlalchemy.orm import Session

from bond_oauth.cipher import TokenCipher
from bond_oauth.errors import OAuthError
from bond_oauth.service import PendingConnection, store_connection, utcnow

HANDOFF_SECONDS = 120
_KIND = "handoff"
_USED: dict[str, float] = {}  # nonce -> exp of a redeemed code; pruned once the code would have expired anyway
_LOCK = threading.Lock()


def forget_handoffs() -> None:
    """Empty the single-use registry (tests). Deprecated with the module: see ``HandoffStore``."""
    with _LOCK:
        _USED.clear()


def _invalid(message: str = "The hand-off code is not valid") -> OAuthError:
    return OAuthError("invalid_handoff", message)


def issue_handoff(pending: PendingConnection, *, cipher: TokenCipher, ttl: int = HANDOFF_SECONDS,
                  now: float | None = None) -> str:
    """Deprecated (use ``HandoffStore.issue``). Seal a native flow's ``PendingConnection`` into a one-time code.
    Shared mailboxes (no owner) are refused."""
    if pending.owner is None:
        raise _invalid("A shared connection cannot be handed off to one user")
    issued = time.time() if now is None else now
    payload = {"kind": _KIND, "sub": pending.owner, "provider": pending.provider,
               "connection_name": pending.connection_name, "fields": pending.fields,
               "nonce": secrets.token_urlsafe(12), "exp": issued + ttl}
    return cipher.encrypt_state(json.dumps(payload, separators=(",", ":")))


def redeem_handoff(session: Session, *, code: str, user_id: str, cipher: TokenCipher, connection_model: Any,
                   expected_provider: str | None = None, now: float | None = None):
    """Deprecated (use ``HandoffStore.redeem``). Store and return the connection row sealed in ``code``, if it is valid, unused, unexpired and ``user_id`` is
    the user who started the flow (and, when ``expected_provider`` is given, the code is for that provider; checked
    before anything is stored or burned). Older live rows of the same (owner, provider, connection_name) are revoked.

    Anything else (damaged, expired, another user's, already used) raises ``OAuthError("invalid_handoff")`` and stores
    nothing. A code is burned only when it would otherwise succeed (and un-burned if the insert fails).
    """
    current = time.time() if now is None else now
    try:
        data = json.loads(cipher.decrypt_state(code or ""))
        if data["kind"] != _KIND:
            raise KeyError("kind")
        sub, nonce, exp = str(data["sub"]), str(data["nonce"]), float(data["exp"])
        provider, name, fields = str(data["provider"]), str(data["connection_name"]), dict(data["fields"])
    except (ValueError, KeyError, TypeError):
        raise _invalid() from None
    if current >= exp:
        raise _invalid("The hand-off code has expired")
    if not user_id or sub != user_id:
        raise _invalid()
    if expected_provider is not None and provider != expected_provider:
        raise _invalid("The hand-off code is for another provider")
    with _LOCK:
        for old, old_exp in list(_USED.items()):
            if old_exp <= current:
                del _USED[old]
        if nonce in _USED:
            raise _invalid("The hand-off code was already used")
        _USED[nonce] = exp
    try:
        return store_connection(session, connection_model, owner=sub, provider=provider, connection_name=name,
                                fields=fields, stamp=utcnow())
    except Exception:
        with _LOCK:
            _USED.pop(nonce, None)
        raise
