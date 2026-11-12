"""The stored inbox. Same database as ``tasks``: the sweep writes the notice inside its claim."""

from bond_notify_py import NoticesMixin

from ..db import Base


class Notice(NoticesMixin, Base):
    """Table ``notices``."""
