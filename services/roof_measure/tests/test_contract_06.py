"""docs/contract-0.6.md is read by tests: the totals table is the engine's key list, the warning codes and the call are the
code's, and the edge types the engine emits are the ones the contract lists. Synthetic data only."""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest

from roof_measure import library
from roof_measure.engine.load import roof_points_from_arrays
from roof_measure.engine.measure import measure_stages
from roof_measure.engine.params import DEFAULT
from roof_measure.engine.synth_extra import extra_cases
from roof_measure.engine.synth_points import cases
from roof_measure.envelope import WARNING_CODES
from roof_measure.model import STEP_EDGE_TYPES, TOTALS_KEYS, VALID_EDGE_TYPES

DOC = (Path(__file__).resolve().parents[3] / "docs" / "contract-0.6.md").read_text()
EDGE_TYPES_IN_CONTRACT = ("eave", "rake", "flat_edge", "ridge", "hip", "valley", "step_flashing", "wall_flashing", "transition",
                          "level_change", "flat_seam")


def section(title: str) -> str:
    m = re.search(rf"^## {re.escape(title)}.*?$(.*?)(?=^## |\Z)", DOC, re.DOTALL | re.MULTILINE)
    assert m, title
    return m.group(1)


def table_keys(text: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r"^\| `([a-z_0-9]+)` \|", text, re.MULTILINE)]


def test_the_totals_table_is_exactly_the_key_list_in_order():
    assert table_keys(section("Totals")) == list(TOTALS_KEYS)
    assert len(set(TOTALS_KEYS)) == len(TOTALS_KEYS) == 24


@pytest.fixture(scope="module")
def measured():
    out = {}
    for c in [*cases(), *extra_cases()]:
        pts = c.points()
        wall = c.roof.wall_polygon()
        rp = roof_points_from_arrays(pts[pts[:, 3] == 1][:, :3], wall, pts)
        res, _ = measure_stages(rp, wall, params=DEFAULT, deadline=None, outline_source="county", parcel_match="given", context=pts)
        if not res.refused:
            out[c.name] = res
    return out


def test_the_engine_writes_exactly_the_contract_keys_and_only_contract_edge_types(measured):
    assert len(measured) >= 40
    seen: set[str] = set()
    for name, res in measured.items():
        assert tuple(res.totals) == TOTALS_KEYS, name
        seen |= {e.type for e in res.edges}
    assert seen <= set(EDGE_TYPES_IN_CONTRACT), seen - set(EDGE_TYPES_IN_CONTRACT)
    assert {"eave", "rake", "ridge", "hip", "valley", "flat_edge", "level_change", "step_flashing"} <= seen  # the cases do exercise them
    assert set(EDGE_TYPES_IN_CONTRACT) <= set(VALID_EDGE_TYPES) and set(STEP_EDGE_TYPES) <= set(EDGE_TYPES_IN_CONTRACT)
    assert all(f"`{t}`" in section("model.facets, edges, objects") for t in EDGE_TYPES_IN_CONTRACT)


def test_the_warning_codes_in_the_contract_are_the_code_list_and_the_removed_ones_are_named():
    text = section("Warning codes")
    listed = re.findall(r"`([a-z_]+)`", text.split("Removed in 0.6.0")[0])
    assert tuple(dict.fromkeys(listed)) == WARNING_CODES
    removed = re.findall(r"`([a-z_]+)`", text.split("Removed in 0.6.0")[1])
    assert len(removed) == 11 and not set(removed) & set(WARNING_CODES)


def test_the_call_in_the_contract_is_the_signature():
    sig = re.search(r"```python\n(.*?)```", section("The call"), re.DOTALL).group(1)
    declared = ast.parse(f"def {sig.strip()}: pass").body[0].args
    assert [x.arg for x in declared.args] == ["address"]
    assert [x.arg for x in declared.kwonlyargs] == [p for p in inspect.signature(library.measure).parameters if p != "address"]
    for gone in ("engine", "method", "hints", "verify"):
        assert gone not in inspect.signature(library.measure).parameters


def test_the_version_in_the_contract_is_the_package_version():
    from roof_measure.version import PIPELINE_VERSION

    assert PIPELINE_VERSION == "0.6.0" and "`pipeline_version` is `0.6.0`" in DOC
