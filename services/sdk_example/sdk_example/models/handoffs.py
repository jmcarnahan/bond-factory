"""One-time native hand-off codes: the lib's mixin attached to the example Base (table ``oauth_handoffs``)."""

from bond_oauth import HandoffsMixin

from ..db import Base


class OAuthHandoff(HandoffsMixin, Base):
    """Used for ``purpose="signin"`` (sign-in native) and ``purpose="connect"`` (connect native)."""
