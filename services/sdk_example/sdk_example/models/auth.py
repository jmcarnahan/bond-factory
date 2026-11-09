"""The example's users table and its two demo identities. Datetimes are naive UTC."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, String, select
from sqlalchemy.orm import Session

from ..db import Base

DEMO_USER_ID = "demo-user-1"
VIEWER_USER_ID = "demo-user-2"
NOT_INVITED_EMAIL = "notinvited@example.com"

#: The seeded users. ``demo-user-1`` can write tasks, read everyone's tasks and manage connections; ``demo-user-2`` is a viewer.
DEMO_USERS: tuple[dict, ...] = (
    {"id": DEMO_USER_ID, "email": "demo@example.com", "name": "Demo User", "initials": "DU",
     "capabilities": ["tasks.write", "tasks.read_all", "connections.manage"]},
    {"id": VIEWER_USER_ID, "email": "viewer@example.com", "name": "Viewer User", "initials": "VU",
     "capabilities": []},
)

#: What the mock verifier knows (written to out/mock_identities.json). ``notinvited@example.com`` has an
#: identity but NO users row, so signing in with it answers 403 not_invited.
MOCK_IDENTITIES: tuple[dict, ...] = (
    {"email": "demo@example.com", "name": "Demo User", "uid": "mock-uid-1"},
    {"email": "viewer@example.com", "name": "Viewer User", "uid": "mock-uid-2"},
    {"email": NOT_INVITED_EMAIL, "name": "Not Invited", "uid": "mock-uid-3"},
)


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    email = Column(String, nullable=False, unique=True)  # always lowercased
    name = Column(String, nullable=False, default="")
    initials = Column(String, nullable=False, default="")
    language = Column(String, nullable=False, default="en")
    capabilities = Column(JSON, nullable=False, default=list)
    is_active = Column(Boolean, nullable=False, default=True)
    accepted_at = Column(DateTime, nullable=True)
    last_sign_in_at = Column(DateTime, nullable=True)
    sessions_valid_after = Column(DateTime, nullable=True)
    firebase_uid = Column(String, nullable=True, unique=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    def public(self) -> dict:
        """The generic ``user`` object of the sign-in answers."""
        return {"id": self.id, "email": self.email, "name": self.name, "initials": self.initials,
                "language": self.language or "en", "capabilities": list(self.capabilities or [])}


def initials_of(name: str) -> str:
    return "".join(part[0] for part in name.split()[:2]).upper()


def ensure_demo_users(session: Session) -> None:
    """Create the demo users when missing (idempotent; an existing row is left as it is). Commits."""
    for row in DEMO_USERS:
        if session.execute(select(User.id).where(User.id == row["id"])).first() is None:
            session.add(User(**row))
    session.commit()
