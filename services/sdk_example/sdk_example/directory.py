"""REPLACE. The one file that knows the users table: `bond_signin.UserDirectory` over `User`. THE FILE AN APP REWRITES.

Every method gets the open database session of the sign-in transaction. Where an app has more rules (company
suspension, an invite list in another table, an audit row) the comment on that method says so.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime

import bond_oauth as oauth
import bond_signin
from bond_auth_py import SessionSpec
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models.auth import User, utcnow
from .oauth_wiring import OAuthWiring

LOGGER = logging.getLogger("sdk_example.signin")
PROVIDER_REFUSALS = frozenset({"invalid_grant", "unauthorized_client", "invalid_client"})


class Directory:
    def __init__(self, wiring: OAuthWiring, *, fake: bool, probe: bool = False) -> None:
        self.wiring, self.fake, self.probe = wiring, fake, probe

    # --- finding the person -----------------------------------------------------------------------------
    def find_by_identity(self, session: Session, provider: str, subject: str) -> User | None:
        return session.scalar(select(User).where(User.identity_provider == provider,
                                                 User.identity_subject == subject))

    def find_by_id(self, session: Session, user_id: str) -> User | None:
        return session.get(User, user_id)

    def find_invite(self, session: Session, emails: Sequence[str], provider: str, *,
                    subject: str | None = None) -> User | None:
        """The invited row for the verified address(es) (already lowercased; the stored e-mail is compared lowercased too). Two different users behind the
        candidates is ambiguous: None, so the person is refused as not invited. An app with an admin e-mail list
        (or a `removed` flag) applies it here, and may create or promote the row inside this transaction.

        `subject` is the provider's id for the person. This example matches by e-mail only; an app that backfilled
        Firebase identities (provider uid to subject) would look the subject up here first and return that row."""
        rows = {u.id: u for u in session.scalars(select(User).where(func.lower(User.email).in_(list(emails))))}
        return next(iter(rows.values())) if len(rows) == 1 else None

    def link_identity(self, session: Session, user: User, provider: str, subject: str) -> None:
        """Bind the provider account to the user, once. The lib calls this only after the identity checks."""
        if self.find_by_identity(session, provider, subject) not in (None, user):
            raise bond_signin.IdentityTaken(f"{provider} account already linked")
        user.identity_provider, user.identity_subject = provider, subject

    # --- rules and the session's content ----------------------------------------------------------------
    def check_allowed(self, session: Session, user: User, provider: str) -> None:
        """Nothing to refuse here. An app raises `company_suspended` or `provider_not_allowed` (an exception
        with that `code` attribute) for a suspended company or a provider its account may not use."""

    def capabilities(self, session: Session, user: User) -> list[str]:
        return list(user.capabilities or [])

    def session_spec(self, session: Session, user: User) -> SessionSpec:
        """The access token's content. Authority is re-read from the row on every request, not from this."""
        return SessionSpec(sub=user.id, name=user.name, capabilities=self.capabilities(session, user),
                           extra_claims={})  # an app adds e.g. {"company_id": user.company_id}

    def public(self, session: Session, user: User) -> dict:
        """The `user` object of every sign-in answer: the same dict as `GET /auth/me`."""
        return user.public()

    # --- bookkeeping ------------------------------------------------------------------------------------
    def record_sign_in(self, session: Session, user: User, *, provider: str, ip: str | None, first: bool) -> None:
        now = utcnow()
        if first:
            user.accepted_at = user.accepted_at or now
        user.last_sign_in_at = now

    def record_refusal(self, session: Session, reason: str, *, email: str | None, user: User | None,
                       provider: str, ip: str | None) -> None:
        """The code only: never the address, token or code. An app writes its audit row here."""
        LOGGER.info("sign-in refused: %s (%s)", reason, provider)

    def mark_sessions_invalid(self, session: Session, user: User, at: datetime) -> None:
        """Sign-out everywhere: sessions whose sign-in is older than `at` die. Naive UTC, like every column."""
        user.sessions_valid_after = at.replace(tzinfo=None)

    def provider_alive(self, session: Session, user: User, provider: str) -> bool | None:
        """OPTIONAL, off by default (SDK_EXAMPLE_PROBE=1): deactivating the user in the app already ends access, so
        the daily provider probe is only for an app that wants a provider-side removal to end sessions too.
        Is the person's provider account still good? None = unknown (fake mode; identity-only sign-in, which
        keeps no connection). Real mode asks the provider through the live connection: a refused refresh token
        (account removed or access revoked) is False and ends the session family. The connection is the ask's, not the identity's: an identity-only
        sign-in has none, so this stays None for it."""
        if self.fake or not self.probe:  # fake: the accounts never go away; probe off: see the docstring
            return None
        from .models.connections import (
            OAuthConnection,  # lazily: an app without connections has no such model
        )
        row = session.scalar(select(OAuthConnection).where(
            OAuthConnection.user_id == user.id, OAuthConnection.provider == provider,
            OAuthConnection.revoked_at.is_(None)))
        impl = self.wiring.providers.get(provider)
        if row is None or impl is None:
            return None
        try:
            oauth.access_token(session, row, provider=impl, cipher=self.wiring.cipher, mark=False)
        except oauth.ReconnectRequired as exc:
            # Only a refusal by the provider means the account is gone. An undecryptable token is OUR problem.
            return False if exc.reason in PROVIDER_REFUSALS else None
        except oauth.RetryableError:
            return None  # the provider is down, which says nothing about the account
        return True
