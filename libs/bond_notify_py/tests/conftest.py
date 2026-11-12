import json
from pathlib import Path

from sqlalchemy.orm import DeclarativeBase

from bond_notify_py import NoticesMixin

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "notify"


class Base(DeclarativeBase):
    pass


class Notice(NoticesMixin, Base):
    pass


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text())
