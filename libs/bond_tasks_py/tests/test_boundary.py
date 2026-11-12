"""The lib imports only sqlalchemy, pydantic and the standard library."""

import ast
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "bond_tasks_py"
ALLOWED = {"sqlalchemy", "pydantic", "bond_tasks_py"}


def imported_roots(path: Path) -> set[str]:
    roots = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            roots |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_only_sqlalchemy_pydantic_and_the_standard_library():
    stdlib = set(sys.stdlib_module_names)
    for path in PACKAGE.rglob("*.py"):
        stray = {r for r in imported_roots(path) if r not in stdlib and r not in ALLOWED}
        assert not stray, f"{path.name} imports {sorted(stray)}"


def test_no_sibling_bond_lib_is_imported():
    for path in PACKAGE.rglob("*.py"):
        sibling = {r for r in imported_roots(path) if r.startswith("bond_") and r != "bond_tasks_py"}
        assert not sibling, f"{path.name} imports {sorted(sibling)}"


def test_no_source_file_is_over_the_line_cap():
    for path in PACKAGE.rglob("*.py"):
        assert len(path.read_text().splitlines()) <= 300, path.name
