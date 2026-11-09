"""The core must stay movable: pydantic, PyJWT, cryptography, sqlalchemy and the standard library only."""

import ast
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "bond_sync_py"
ALLOWED = {"pydantic", "jwt", "cryptography", "sqlalchemy"}


def _imports(path: Path):
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0], node.lineno, 0
        elif isinstance(node, ast.ImportFrom):
            yield (node.module or "").split(".")[0], node.lineno, node.level


def test_only_allowed_third_party_imports():
    offenders = []
    for path in sorted(PKG.glob("*.py")):
        for root, line, level in _imports(path):
            if level:  # relative import inside the package
                continue
            if root in sys.stdlib_module_names or root in ("bond_sync_py", "__future__"):
                continue
            if root not in ALLOWED:
                offenders.append(f"{path.name}:{line} imports {root}")
    assert offenders == []


def test_no_sibling_bond_libs_or_web_frameworks():
    text = "\n".join(p.read_text() for p in PKG.glob("*.py"))
    for name in ("bond_service_kit", "bond_auth_py", "bond_jobs", "bond_storage", "fastapi", "starlette"):
        assert f"import {name}" not in text and f"from {name}" not in text


def test_source_files_stay_under_the_soft_cap():
    for path in PKG.glob("*.py"):
        assert len(path.read_text().splitlines()) <= 300, path.name
