"""OAuth2 flows and encrypted token storage for Google and Microsoft."""

from bond_oauth import pkce
from bond_oauth.cipher import TokenCipher
from bond_oauth.errors import OAuthError, ProviderError, ReconnectRequired, RetryableError
from bond_oauth.fake import FakeOAuth
from bond_oauth.google import GoogleOAuth
from bond_oauth.handoff import issue_handoff, redeem_handoff
from bond_oauth.handoff_store import HandoffsMixin, HandoffStore
from bond_oauth.identity import OidcIdentity, identity_from_token_response
from bond_oauth.microsoft import MicrosoftOAuth
from bond_oauth.models import ConnectionsMixin
from bond_oauth.providers import OAuthProvider, TokenSet
from bond_oauth.scopes import (
    GOOGLE_CALENDAR,
    GOOGLE_DEFAULT,
    GOOGLE_MAIL_SEND,
    GOOGLE_SIGNIN,
    MICROSOFT_BASE,
    MICROSOFT_OFFICE,
    MICROSOFT_SIGNIN,
    MICROSOFT_SIGNIN_FULL,
    is_identity_only,
    scope_drift,
)
from bond_oauth.service import (
    ConnectionStatus,
    PendingConnection,
    StartedFlow,
    access_token,
    complete,
    disconnect,
    forget_access,
    start,
    start_flow,
    status,
)
from bond_oauth.signin import SignInFlow, SignInResult, StartedSignIn, StateInfo
from bond_oauth.state import StatePayload, decode_state, encode_state

__version__ = "0.2.0"

__all__ = [
    "GOOGLE_CALENDAR", "GOOGLE_DEFAULT", "GOOGLE_MAIL_SEND", "GOOGLE_SIGNIN", "MICROSOFT_BASE", "MICROSOFT_OFFICE",
    "MICROSOFT_SIGNIN", "MICROSOFT_SIGNIN_FULL", "ConnectionStatus", "ConnectionsMixin", "FakeOAuth", "GoogleOAuth",
    "HandoffStore", "HandoffsMixin", "MicrosoftOAuth", "OAuthError", "OAuthProvider", "OidcIdentity",
    "PendingConnection", "ProviderError", "ReconnectRequired", "RetryableError", "SignInFlow", "SignInResult",
    "StartedFlow", "StartedSignIn", "StateInfo", "StatePayload", "TokenCipher", "TokenSet", "access_token", "complete",
    "decode_state", "disconnect", "encode_state", "forget_access", "identity_from_token_response", "is_identity_only",
    "issue_handoff", "pkce", "redeem_handoff", "scope_drift", "start", "start_flow", "status",
]
