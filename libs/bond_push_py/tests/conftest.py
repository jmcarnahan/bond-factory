import json
from pathlib import Path

from sqlalchemy.orm import DeclarativeBase

from bond_push_py import PushDevicesMixin

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "push"


class Base(DeclarativeBase):
    pass


class PushDevice(PushDevicesMixin, Base):
    pass


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text())
