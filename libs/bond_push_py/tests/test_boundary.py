"""The lib imports only its declared dependencies and the standard library, and no sibling bond lib."""

import ast
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "bond_push_py"
ALLOWED = {"sqlalchemy", "httpx", "jwt", "cryptography", "bond_push_py"}


def imported_roots(path: Path) -> set[str]:
    roots = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            roots |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_only_declared_dependencies_and_the_standard_library():
    stdlib = set(sys.stdlib_module_names)
    for path in PACKAGE.rglob("*.py"):
        stray = {r for r in imported_roots(path) if r not in stdlib and r not in ALLOWED}
        assert not stray, f"{path.name} imports {sorted(stray)}"


def test_no_sibling_bond_lib_is_imported():
    for path in PACKAGE.rglob("*.py"):
        sibling = {r for r in imported_roots(path) if r.startswith("bond_") and r != "bond_push_py"}
        assert not sibling, f"{path.name} imports {sorted(sibling)}"


def test_no_source_file_is_over_the_line_cap():
    for path in PACKAGE.rglob("*.py"):
        assert len(path.read_text().splitlines()) <= 300, path.name


def test_importing_the_apns_module_does_not_need_h2():
    assert "h2" not in imported_roots(PACKAGE / "apns.py")
