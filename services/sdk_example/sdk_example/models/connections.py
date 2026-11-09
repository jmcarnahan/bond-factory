"""The example's one OAuth connections table (the lib's mixin attached to the example Base)."""

from bond_oauth.models import ConnectionsMixin

from ..db import Base


class OAuthConnection(ConnectionsMixin, Base):
    """Table ``oauth_connections``; ``user_id`` references the example's ``users`` table."""
