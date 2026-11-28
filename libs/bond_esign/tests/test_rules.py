"""The library rules of the project, checked by reading the package source."""

import re
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "bond_esign"
SOURCES = sorted(PACKAGE.rglob("*.py"))

FORBIDDEN = {
    "os.environ": r"\bos\.environ\b",
    "getenv": r"\bgetenv\b",
    "utcnow": r"\butcnow\b",
    "time.time(": r"\btime\.time\(",
    "import fastapi": r"^\s*import\s+fastapi\b",
    "from fastapi": r"^\s*from\s+fastapi\b",
}


def _hits(pattern: str, allowed: set[str] = frozenset()):
    found = []
    for path in SOURCES:
        if path.name in allowed:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if re.search(pattern, line):
                found.append(f"{path.name}:{number}: {line.strip()}")
    return found


def test_the_package_source_is_found():
    assert len(SOURCES) > 20 and PACKAGE / "service.py" in SOURCES


def test_no_environment_clock_or_web_framework_in_the_library():
    for name, pattern in FORBIDDEN.items():
        assert _hits(pattern) == [], name


def test_the_wall_clock_is_read_only_in_certs():
    assert _hits(r"\bdatetime\.now\b", allowed={"certs.py"}) == []


def test_no_sibling_bond_library_is_imported():
    pattern = r"^\s*(?:from|import)\s+(bond_(?!esign\b)\w+)"
    assert _hits(pattern) == []
    assert _hits(r"""importlib\.import_module\(\s*["']bond_(?!esign\b)""") == []


def test_the_patterns_do_match_what_they_are_meant_to_catch():
    samples = {
        "os.environ": "x = os.environ['A']", "getenv": "os.getenv('A')", "utcnow": "datetime.utcnow()",
        "time.time(": "t = time.time()", "import fastapi": "import fastapi", "from fastapi": "from fastapi import X",
    }
    for name, line in samples.items():
        assert re.search(FORBIDDEN[name], line), name
    assert re.search(r"\bdatetime\.now\b", "datetime.now(UTC)")
    assert re.search(r"^\s*(?:from|import)\s+(bond_(?!esign\b)\w+)", "from bond_jobs import x")
    assert not re.search(r"^\s*(?:from|import)\s+(bond_(?!esign\b)\w+)", "from bond_esign import x")
