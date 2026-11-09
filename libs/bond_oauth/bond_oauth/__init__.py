"""OAuth2 flows and encrypted token storage for Google and Microsoft."""

from bond_oauth import pkce
from bond_oauth.cipher import TokenCipher
from bond_oauth.errors import OAuthError, ProviderError, ReconnectRequired, RetryableError
from bond_oauth.fake import FakeOAuth
from bond_oauth.google import GoogleOAuth
from bond_oauth.microsoft import MicrosoftOAuth
from bond_oauth.models import ConnectionsMixin
from bond_oauth.providers import OAuthProvider, TokenSet
from bond_oauth.scopes import GOOGLE_DEFAULT, MICROSOFT_BASE, MICROSOFT_OFFICE, scope_drift
from bond_oauth.service import (
    ConnectionStatus,
    StartedFlow,
    access_token,
    complete,
    disconnect,
    forget_access,
    start,
    start_flow,
    status,
)
from bond_oauth.state import StatePayload, decode_state, encode_state

__version__ = "0.1.0"

__all__ = [
    "GOOGLE_DEFAULT", "MICROSOFT_BASE", "MICROSOFT_OFFICE", "ConnectionStatus", "ConnectionsMixin", "FakeOAuth",
    "GoogleOAuth", "MicrosoftOAuth", "OAuthError", "OAuthProvider", "ProviderError", "ReconnectRequired",
    "RetryableError", "StartedFlow", "StatePayload", "TokenCipher", "TokenSet", "access_token", "complete", "decode_state",
    "disconnect", "encode_state", "forget_access", "pkce", "scope_drift", "start", "start_flow", "status",
]
