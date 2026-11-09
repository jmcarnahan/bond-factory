"""Direct Google/Microsoft sign-in: Protocol seams, scope policy, router factory."""

from .errors import MESSAGES, STATUS_FOR_CODE, IdentityTaken, SignInRefused, http_error, refusal_code
from .finish import CookiePolicy, clear_session_cookies, finish_session
from .order import sign_in, sign_in_with_first
from .origin import require_origin
from .policy import ScopePolicy, ScopeSet, UnknownScopeSet, connect_scopes, normalize_email, wanted_sets
from .protocols import (
    HandoffStore,
    IdentityFlow,
    IssuedSession,
    OidcIdentity,
    SessionIssuer,
    SessionSpec,
    SignInResult,
    StartedSignIn,
    StateInfo,
    UserDirectory,
    UserRef,
)
from .router import make_signin_router
from .settings import SignInSettings, from_env

__version__ = "0.1.0"

__all__ = [
    "MESSAGES",
    "STATUS_FOR_CODE",
    "CookiePolicy",
    "HandoffStore",
    "IdentityFlow",
    "IdentityTaken",
    "IssuedSession",
    "OidcIdentity",
    "ScopePolicy",
    "ScopeSet",
    "SessionIssuer",
    "SessionSpec",
    "SignInRefused",
    "SignInResult",
    "SignInSettings",
    "StartedSignIn",
    "StateInfo",
    "UnknownScopeSet",
    "UserDirectory",
    "UserRef",
    "clear_session_cookies",
    "connect_scopes",
    "finish_session",
    "from_env",
    "http_error",
    "make_signin_router",
    "normalize_email",
    "refusal_code",
    "require_origin",
    "sign_in",
    "sign_in_with_first",
    "wanted_sets",
]
