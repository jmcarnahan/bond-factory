"""Declarative mixin for the ``push_devices`` table.

    class PushDevice(PushDevicesMixin, Base): ...

One row per (user, device). ``environment`` ("sandbox" or "production") must match the token: the two Apple hosts
are not interchangeable. The lib ships no migration; ``PUSH_DEVICE_COLUMNS`` is the contract a test pins.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, String, UniqueConstraint
from sqlalchemy.orm import declared_attr

PLATFORMS = ("ios",)  # the only platform a sender in this lib can deliver to (APNs)
ENVIRONMENTS = ("sandbox", "production")


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


#: column name -> nullable. The literal contract of the ``push_devices`` table; tests pin it.
PUSH_DEVICE_COLUMNS: dict[str, bool] = {
    "id": False,
    "user_id": False,
    "device_id": False,
    "token": False,
    "platform": False,
    "environment": False,
    "topic": True,
    "last_seen_at": False,
    "disabled_at": True,
    "created_at": False,
}


class PushDevicesMixin:
    __tablename__ = "push_devices"

    @declared_attr.directive
    def __table_args__(cls):
        return (UniqueConstraint("user_id", "device_id", name="uq_push_devices_user_device"),)

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, nullable=False, index=True)
    device_id = Column(String(64), nullable=False)
    token = Column(String(255), nullable=False, unique=True)
    platform = Column(String(8), nullable=False)  # "ios", "android", "web"
    environment = Column(String(12), nullable=False)  # "sandbox" | "production"
    topic = Column(String(255), nullable=True)  # the app's bundle id (apns-topic)
    last_seen_at = Column(DateTime, nullable=False, default=_utcnow)
    disabled_at = Column(DateTime, nullable=True)  # set when the token is unregistered
    created_at = Column(DateTime, nullable=False, default=_utcnow)
