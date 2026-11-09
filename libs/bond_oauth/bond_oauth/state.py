"""Stateless OAuth ``state``: an encrypted payload, so no table is needed and the PKCE verifier stays secret."""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass

from bond_oauth.cipher import TokenCipher
from bond_oauth.errors import OAuthError

STATE_SECONDS = 600


@dataclass(frozen=True)
class StatePayload:
    sub: str
    provider: str
    connection_name: str
    nonce: str
    exp: float
    verifier: str
    redirect_to: str
    shared: bool = False
    native: bool = False  # a phone-app flow: no browser binding; the result is handed off with a one-time code


def encode_state(cipher: TokenCipher, *, sub: str, provider: str, connection_name: str, verifier: str,
                 redirect_to: str, shared: bool = False, native: bool = False, now: float | None = None) -> str:
    """``now`` is epoch seconds on the REAL clock (tests pass a past value to make an expired state)."""
    issued = time.time() if now is None else now
    payload = {"sub": sub, "provider": provider, "connection_name": connection_name,
               "nonce": secrets.token_urlsafe(12), "exp": issued + STATE_SECONDS, "verifier": verifier,
               "redirect_to": redirect_to, "shared": shared, "native": native}
    return cipher.encrypt_state(json.dumps(payload, separators=(",", ":")))


def decode_state(cipher: TokenCipher, state: str, *, now: float | None = None) -> StatePayload:
    """``OAuthError("invalid_state")`` for anything not minted by this key, ``"expired_state"`` after 10 minutes."""
    try:
        data = json.loads(cipher.decrypt_state(state or ""))
        payload = StatePayload(sub=str(data["sub"]), provider=str(data["provider"]),
                               connection_name=str(data["connection_name"]), nonce=str(data["nonce"]),
                               exp=float(data["exp"]), verifier=str(data["verifier"]),
                               redirect_to=str(data.get("redirect_to") or ""), shared=bool(data.get("shared")),
                               native=bool(data.get("native")))
    except (ValueError, KeyError, TypeError) as exc:
        raise OAuthError("invalid_state", "The sign-in link is not valid") from exc
    if (time.time() if now is None else now) >= payload.exp:  # expired AT exp, like a JWT
        raise OAuthError("expired_state", "The sign-in link has expired")
    return payload
