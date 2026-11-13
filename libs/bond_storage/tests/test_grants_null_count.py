"""A legacy grants table may hold NULL in the count column (the mixin says NOT NULL, the old table never did)."""

from datetime import datetime, timedelta

import pytest
import sqlalchemy as sa
from conftest import Base, Document, load_document
from sqlalchemy.orm import mapped_column

from bond_storage import GrantsMixin, claim, has_live_link, hash_token, resolve

NOW = datetime(2030, 1, 1, 12, 0)


class LegacyGrant(GrantsMixin, Base):
    __tablename__ = "legacy_null_grants"
    download_count = mapped_column("hits", sa.Integer, nullable=True)


@pytest.fixture
def row(factory):
    with factory() as session:
        session.add(Document(id="d1", storage_key="k", filename="a.pdf"))
        session.add(LegacyGrant(id="g1", token_hash=hash_token("tok"), document_id="d1", owner_type="x", owner_id="o1",
                                expires_at=NOW + timedelta(days=1), max_downloads=2, download_count=None))
        session.commit()
    return factory


def look(session):
    return resolve(session, "tok", grant_model=LegacyGrant, document_loader=load_document, now=lambda: NOW)[0]


def test_a_null_count_resolves_and_claims_once_per_download(row):
    with row() as session:
        grant = look(session)
        assert claim(session, grant, "10.0.0.1", now=lambda: NOW) is True
        assert grant.download_count == 1
        assert claim(session, grant, now=lambda: NOW) is True
        assert grant.download_count == 2


def test_the_cap_still_stops_a_null_count_link(row):
    with row() as session:
        grant = look(session)
        assert [claim(session, grant, now=lambda: NOW) for _ in range(3)] == [True, True, False]


def test_a_null_count_link_is_live(row):
    with row() as session:
        assert has_live_link(session, "x", "o1", grant_model=LegacyGrant, now=lambda: NOW) is True


def test_enforce_cap_off_still_counts_from_null(row):
    with row() as session:
        grant = look(session)
        assert claim(session, grant, enforce_cap=False, now=lambda: NOW) is True
        assert grant.download_count == 1
