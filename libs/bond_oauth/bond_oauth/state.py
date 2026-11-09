"""Stateless OAuth ``state``: an encrypted payload, so no table is needed and the PKCE verifier stays secret."""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass

from bond_oauth.cipher import TokenCipher
from bond_oauth.errors import OAuthError

STATE_SECONDS = 600
INTENTS = ("connect", "signin")


@dataclass(frozen=True)
class StatePayload:
    sub: str | None  # the connecting user; None only for a sign-in (nobody is known yet)
    provider: str
    connection_name: str
    nonce: str
    exp: float
    verifier: str
    redirect_to: str
    shared: bool = False
    native: bool = False  # a phone-app flow: no browser binding; the result is handed off with a one-time code
    intent: str = "connect"  # "connect" (add a connection to a user) or "signin" (identify a person)
    device_hash: str | None = None  # sha256 hex of the phone's device secret (native sign-in)
    attempt_id: str | None = None  # opaque id the app echoes back
    oidc_nonce: str | None = None  # the OIDC ``nonce`` sent to the provider (sha256 hex of ``nonce``)
    set_id: str | None = None  # the role scope set a connect flow is asking for
    login_hint: str | None = None
    expected_subject: str | None = None  # connect: the identity subject the account must have (account binding)


_OPTIONAL = ("device_hash", "attempt_id", "oidc_nonce", "set_id", "login_hint", "expected_subject")


def encode_state(cipher: TokenCipher, *, sub: str | None, provider: str, connection_name: str, verifier: str,
                 redirect_to: str, shared: bool = False, native: bool = False, intent: str = "connect",
                 device_hash: str | None = None, attempt_id: str | None = None, oidc_nonce: str | None = None,
                 set_id: str | None = None, login_hint: str | None = None, expected_subject: str | None = None,
                 nonce: str | None = None, now: float | None = None) -> str:
    """``now`` is epoch seconds on the REAL clock (tests pass a past value to make an expired state).

    ``nonce`` is minted when not given; a sign-in passes its own because the OIDC nonce derives from it.
    Unset optional fields are left out so the encrypted text stays short (a sign-in state is about 700 chars).
    """
    issued = time.time() if now is None else now
    payload: dict[str, object] = {
        "sub": sub, "provider": provider, "connection_name": connection_name,
        "nonce": nonce or secrets.token_urlsafe(12), "exp": issued + STATE_SECONDS, "verifier": verifier,
        "redirect_to": redirect_to, "shared": shared, "native": native, "intent": intent}
    extra = {"device_hash": device_hash, "attempt_id": attempt_id, "oidc_nonce": oidc_nonce, "set_id": set_id,
             "login_hint": login_hint, "expected_subject": expected_subject}
    payload.update({key: value for key, value in extra.items() if value is not None})
    return cipher.encrypt_state(json.dumps(payload, separators=(",", ":")))


def _opt(data: dict, key: str) -> str | None:
    value = data.get(key)
    return None if value is None else str(value)


def decode_state(cipher: TokenCipher, state: str, *, now: float | None = None) -> StatePayload:
    """``OAuthError("invalid_state")`` for anything not minted by this key, ``"expired_state"`` after 10 minutes.
    A state without ``intent`` (minted before 0.2.0) is a ``connect`` state; ``sub`` None stays None."""
    try:
        data = json.loads(cipher.decrypt_state(state or ""))
        intent = str(data.get("intent") or "connect")
        sub = _opt(data, "sub")
        if intent not in INTENTS or (intent == "connect" and sub is None):
            raise ValueError("intent")
        payload = StatePayload(sub=sub, provider=str(data["provider"]),
                               connection_name=str(data["connection_name"]), nonce=str(data["nonce"]),
                               exp=float(data["exp"]), verifier=str(data["verifier"]),
                               redirect_to=str(data.get("redirect_to") or ""), shared=bool(data.get("shared")),
                               native=bool(data.get("native")), intent=intent,
                               **{key: _opt(data, key) for key in _OPTIONAL})
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise OAuthError("invalid_state", "The sign-in link is not valid") from exc
    if (time.time() if now is None else now) >= payload.exp:  # expired AT exp, like a JWT
        raise OAuthError("expired_state", "The sign-in link has expired")
    return payload
