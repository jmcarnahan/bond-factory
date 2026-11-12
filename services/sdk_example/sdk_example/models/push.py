"""Phone push registrations (one row per user and device)."""

from bond_push_py import PushDevicesMixin

from ..db import Base


class PushDevice(PushDevicesMixin, Base):
    """Table ``push_devices``."""
