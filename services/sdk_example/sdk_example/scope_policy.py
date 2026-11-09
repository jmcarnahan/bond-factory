"""REPLACE. What each provider is asked for, and who is asked for more. An app writes its own version of this file.

Sign-in itself asks for the least that works. Roles that need mail or calendar are asked AFTER sign-in, through the
connect flow, so, at Google, a person who lacks the role (crew here) is never shown a consent screen for access they do not use.
Microsoft is different: the full scope set is asked at sign-in for EVERYONE, because the tenant admin pre-consented
it (no consent screen), so there is no per-role ask. Only Google asks per capability.
"""

from __future__ import annotations

from bond_oauth import GOOGLE_CALENDAR, GOOGLE_MAIL_SEND, GOOGLE_SIGNIN, MICROSOFT_SIGNIN_FULL
from bond_signin import ScopePolicy, ScopeSet

# fake-* names contain neither "google" nor "microsoft" at the start, so the lib's provider-name branches (Google
# include_granted_scopes merging, Microsoft scope union) do not apply; connect_helpers.scopes_for compensates in fake mode.
FAKE_GOOGLE, FAKE_MICROSOFT = "fake-google", "fake-microsoft"
MANAGE = "connections.manage"  # the capability whose holders are asked to connect mail and calendar


def build_policy(google: str, microsoft: str) -> ScopePolicy:
    """``google`` and ``microsoft`` are the registered provider names (fake names in fake mode)."""
    return ScopePolicy(
        signin={google: tuple(GOOGLE_SIGNIN), microsoft: tuple(MICROSOFT_SIGNIN_FULL)},
        by_capability={MANAGE: (
            ScopeSet("mail_send", google, tuple(GOOGLE_MAIL_SEND), "Send mail"),
            ScopeSet("calendar", google, tuple(GOOGLE_CALENDAR), "Calendar"),
        )},
    )


def set_scopes(policy: ScopePolicy) -> dict[str, list[str]]:
    """Set id to its scopes: what the fake provider needs to leave a declined set out of the grant."""
    return {item.id: list(item.scopes) for sets in policy.by_capability.values() for item in sets}
