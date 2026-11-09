"""The identity janitor (opt-in housekeeping after a refused ``not_invited`` sign-in).

Google and Apple create an identity-provider user on first use, so a stranger who taps the button would leave one
behind. ``janitor_after_refusal`` deletes that stray identity when ALL of these hold:

- the token's sign-in provider is ``google.com`` or ``apple.com``;
- no users row has the uid or the lowercased e-mail (asked once, and again right before the delete: an invite may
  have landed in between, and the caller's callable should end its read snapshot first, e.g. roll back);
- the identity was created less than ``window_seconds`` ago on the REAL clock (up to ``skew`` seconds in the
  future is tolerated: the provider's clock can run ahead of ours);
- its provider list is exactly that one provider (a password or a second provider means a real account).

Call it only on sign-in, never on refresh, and only after ``not_invited``. It never raises: whatever goes wrong
the answer is still the 403.
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from bond_auth_py.admin import IdentityAdmin
from bond_auth_py.verify import Identity

LOGGER = logging.getLogger(__name__)

JANITOR_PROVIDERS = frozenset({"google.com", "apple.com"})


def _naive_utc(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value


def janitor_after_refusal(*, identity: Identity, admin: IdentityAdmin, user_exists: Callable[[str, str], bool],
                          now: datetime, audit: Callable[[str, str], None] | None = None,
                          window_seconds: int = 60, skew: int = 5) -> bool:
    """True only when the stray identity was deleted. ``user_exists(uid, email)`` answers "does the app have a
    users row for this uid or e-mail"; ``audit(uid, provider)`` records the deletion."""
    provider, uid = identity.sign_in_provider, identity.uid
    if provider not in JANITOR_PROVIDERS or not uid:
        return False
    try:
        if user_exists(uid, identity.email):
            return False
        user = admin.get_user(uid=uid)
        if user is None or user.get("created_at") is None:
            return False
        age = _naive_utc(now) - _naive_utc(user["created_at"])
        if list(user.get("providers") or []) != [provider]:
            return False
        if not (-timedelta(seconds=skew) <= age < timedelta(seconds=window_seconds)):
            return False
        if user_exists(uid, identity.email):  # asked again immediately before the delete
            return False
        admin.delete_user(uid)
    except Exception as exc:  # noqa: BLE001 - identity gone, provider down, the app's callable failing: still a 403
        LOGGER.warning("identity janitor could not clean up: %s", type(exc).__name__)
        return False
    if audit is not None:
        try:
            audit(uid, provider)
        except Exception as exc:  # noqa: BLE001 - housekeeping must never raise
            LOGGER.warning("identity janitor audit failed: %s", type(exc).__name__)
    return True
