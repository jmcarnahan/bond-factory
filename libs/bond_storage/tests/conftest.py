import pytest
import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from bond_storage import GrantsMixin


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(sa.String, primary_key=True)
    storage_key: Mapped[str] = mapped_column(sa.String)
    filename: Mapped[str] = mapped_column(sa.String)
    content_type: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    kind: Mapped[str] = mapped_column(sa.String, default="doc")
    owner_type: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    owner_id: Mapped[str | None] = mapped_column(sa.String, nullable=True)


class Grant(GrantsMixin, Base):
    __table_args__ = (sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),)


def load_document(session: Session, document_id: str):
    return session.get(Document, document_id)


@pytest.fixture
def factory():
    engine = sa.create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def session(factory):
    with factory() as s:
        yield s


@pytest.fixture
def doc(session):
    d = Document(id="d1", storage_key="c/1/private/a.pdf", filename="a.pdf", content_type="application/pdf",
                 kind="estimate", owner_type="estimate", owner_id="e1")
    session.add(d)
    session.commit()
    return d
