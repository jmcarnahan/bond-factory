"""The models of an app that already exists.

Each lib mixin is attached the way an adopter attaches it: a column the legacy table spells differently is
overridden by attribute (`mirror_enabled = Column("sync_to_calendar", ...)`), and the app's own columns sit beside.
"""

from __future__ import annotations

import sqlalchemy as sa
from bond_push_py import PushDevicesMixin
from bond_storage import GrantsMixin
from bond_tasks_py import TasksMixin, TaskUserSettingsMixin
from sqlalchemy import Boolean, Column, String
from sqlalchemy.orm import mapped_column

from .db import Base

#: The app's own task columns: the lib stores what `host_columns` names and `rules.prepare` approves.
HOST_COLUMNS = ("client_ref", "case_ref")


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    is_admin = Column(Boolean, nullable=False, default=False)


class Client(Base):
    __tablename__ = "clients"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)


class Case(Base):
    __tablename__ = "cases"
    id = Column(String, primary_key=True)
    client_id = Column(String, nullable=True)
    label = Column(String, nullable=False)


class Task(TasksMixin, Base):
    """The legacy `tasks` table: three lib attributes live in columns the app named first."""

    mirror_enabled = Column("sync_to_calendar", Boolean, nullable=False, default=True)
    external_event_id = Column("calendar_event_id", String, nullable=True)
    external_account_user_id = Column("calendar_event_user_id", String, nullable=True)
    client_ref = Column(String, nullable=True)
    case_ref = Column(String, nullable=True)


class Attachment(Base):
    """The app's document table: what `bond_storage` calls a document."""

    __tablename__ = "attachments"
    id = Column(String(64), primary_key=True)
    storage_key = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    content_type = Column(String, nullable=True)
    kind = Column(String, nullable=False, default="file")
    owner_type = Column(String, nullable=True)
    owner_id = Column(String, nullable=True)


class ShareGrant(GrantsMixin, Base):
    """A legacy grants table: other names for three columns, a nullable count and `created_at`, one app column."""

    __tablename__ = "file_share_grants"

    document_id = mapped_column("attachment_id", sa.String(64), nullable=False, index=True)
    created_by = mapped_column("sender_id", sa.String(64), nullable=True)
    download_count = mapped_column("hits", sa.Integer, nullable=True)
    created_at = mapped_column(sa.DateTime, nullable=True)
    recipient_note = mapped_column(sa.String, nullable=True)


class UserPrefs(TaskUserSettingsMixin, Base):
    """A legacy settings table: the four preference columns are named `tz`, `day_start`, `day_end`, `remind_lead`."""

    __tablename__ = "user_prefs"

    user_id = Column("uid", String, primary_key=True)
    time_zone = Column("tz", String(64), nullable=True)
    start_of_day = Column("day_start", String(5), nullable=True)
    end_of_day = Column("day_end", String(5), nullable=True)
    lead_minutes = Column("remind_lead", sa.Integer, nullable=True)
    theme = Column(String, nullable=True)


class PushDevice(PushDevicesMixin, Base):
    """A table the app did not have: the adoption migration creates it, the mixin's columns as they are."""
