import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "capture"


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text())
