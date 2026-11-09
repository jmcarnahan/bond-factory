"""The example's users table and its demo identities. Datetimes are naive UTC."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, String, UniqueConstraint, false, select
from sqlalchemy.orm import Session

from ..db import Base

DEMO_USER_ID = "demo-user-1"
VIEWER_USER_ID = "demo-user-2"
CREW_USER_ID = "demo-user-3"
MS_USER_ID = "demo-user-4"
NOT_INVITED_EMAIL = "notinvited@example.com"  # has a Firebase mock identity but no row
UNINVITED_EMAIL = "uninvited@example.com"  # the fake provider's uninvited identity: no row

#: The seeded users (invited rows: nobody has signed in yet). ``demo-user-1`` can write tasks, read everyone's tasks
#: and manage connections (so the policy wants mail and calendar from it); ``demo-user-2`` is a viewer;
#: ``crew@example.com`` has no ``connections.manage`` (nothing wanted); ``demo.microsoft@example.com`` is the
#: fake-microsoft demo identity, bound on its first sign-in. There is NO row for ``uninvited@example.com``.
#: `demo@example.com` is also the break-glass owner row (`allow_password`).
#: The same list, minus ids, is in fixtures/signin/seed_identities.json.
DEMO_USERS: tuple[dict, ...] = (
    {"id": DEMO_USER_ID, "email": "demo@example.com", "name": "Demo User", "initials": "DU",
     "capabilities": ["tasks.write", "tasks.read_all", "connections.manage"], "allow_password": True},
    {"id": VIEWER_USER_ID, "email": "viewer@example.com", "name": "Viewer User", "initials": "VU",
     "capabilities": []},
    {"id": CREW_USER_ID, "email": "crew@example.com", "name": "Crew Member", "initials": "CM",
     "capabilities": ["tasks.write"]},
    {"id": MS_USER_ID, "email": "demo.microsoft@example.com", "name": "Demo Microsoft", "initials": "DM",
     "capabilities": ["tasks.write", "connections.manage"]},
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
    # One person, one identity per provider account: the pair is unique once bound (both NULL until first sign-in).
    __table_args__ = (UniqueConstraint("identity_provider", "identity_subject", name="uq_users_identity"),)

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
    # Bound on the first direct sign-in (Google: sub; Microsoft: tid:oid). The e-mail only finds the invite once.
    identity_provider = Column(String, nullable=True)
    identity_subject = Column(String, nullable=True)
    # Break-glass: only a row with this flag may use the Firebase e-mail and password route.
    allow_password = Column(Boolean, nullable=False, default=False, server_default=false())
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    @property
    def identity(self) -> tuple[str, str] | None:
        """The bound ``(provider, subject)``: what ``bond_signin.UserRef`` calls ``identity``."""
        if self.identity_provider and self.identity_subject:
            return self.identity_provider, self.identity_subject
        return None

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
