"""Refresh sessions: the lib's mixin attached to the example Base (table ``auth_sessions``)."""

from bond_auth_py import SessionsMixin

from ..db import Base


class AuthSession(SessionsMixin, Base):
    """One row per refresh token; ``user_id`` references ``users.id``. An app copies this file as it is."""
