"""Shared test support for the due-instant, permissions and write-path tests: fakes and fixtures. Loaded by
conftest as a pytest plugin.

conftest's ``Base`` already has a ``tasks`` table. A test that needs a Task model with extra app columns uses
``HostTask`` here, which lives on its own declarative base.
"""

import pytest
from sqlalchemy import Column, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from bond_tasks_py import TasksMixin, UserPrefs

HostBase = declarative_base()


class HostTask(TasksMixin, HostBase):
    """A task table with the three app columns an app typically adds."""

    contact_id = Column(String, nullable=True)
    loan_id = Column(String, nullable=True)
    external_ref = Column(String, nullable=True)


class MapPrefs:
    """A ``Preferences`` backed by a dict of user id to ``UserPrefs``; unknown users get the defaults."""

    def __init__(self, **by_user: UserPrefs):
        self.by_user = by_user

    def for_user(self, session, user_id):
        return self.by_user.get(user_id, UserPrefs())


class CoOfficer:
    """u3 may edit and complete every task, but not own."""

    def can_edit(self, task, user_id):
        return user_id in (task.owner_user_id, task.assigned_user_id, "u3")

    def can_own(self, task, user_id):
        return user_id == task.owner_user_id

    def can_complete(self, task, user_id):
        return self.can_edit(task, user_id)


class Admin:
    """u9 may do anything to any task."""

    def can_edit(self, task, user_id):
        return user_id in (task.owner_user_id, task.assigned_user_id, "u9")

    def can_own(self, task, user_id):
        return user_id in (task.owner_user_id, "u9")

    def can_complete(self, task, user_id):
        return self.can_edit(task, user_id)


class Anyone:
    """Anyone may complete or reopen; editing and owning stay with the defaults."""

    def can_edit(self, task, user_id):
        return user_id in (task.owner_user_id, task.assigned_user_id)

    def can_own(self, task, user_id):
        return user_id == task.owner_user_id

    def can_complete(self, task, user_id):
        return True


@pytest.fixture
def host_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    HostBase.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as s:
        yield s
