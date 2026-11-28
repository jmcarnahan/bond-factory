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
from roof_measure.model import (
    OBJECT_KINDS,
    SCHEMA_ONLY_EDGE_TYPES,
    STEP_EDGE_TYPES,
    TOTALS_KEYS,
    VALID_EDGE_TYPES,
)

DOC = (Path(__file__).resolve().parents[3] / "docs" / "contract-0.6.md").read_text()


def section(title: str) -> str:
    m = re.search(rf"^## {re.escape(title)}.*?$(.*?)(?=^## |\Z)", DOC, re.DOTALL | re.MULTILINE)
    assert m, title
    return m.group(1)


def table_keys(text: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r"^\| `([a-z_0-9]+)` \|", text, re.MULTILINE)]


def contract_edge_types() -> set[str]:
    para = " ".join(section("model.facets, edges, objects").split()).split("can emit, and only these:")[1].split(". A step edge")[0]
    return set(re.findall(r"`([a-z_]+)`", para.split("(a drawn line")[0])) | {"flat_seam"}


def test_the_contract_lists_exactly_the_edge_types_and_object_kinds_the_code_knows():
    assert contract_edge_types() == set(VALID_EDGE_TYPES) - set(SCHEMA_ONLY_EDGE_TYPES)
    para = " ".join(section("model.facets, edges, objects").split())
    kinds = re.search(r"`kind` is ((?:`\w+`(?:, | or )?)+)", para).group(1)
    assert tuple(re.findall(r"`(\w+)`", kinds)) == OBJECT_KINDS


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
        out[c.name] = res
    return out


REFUSED = {"complex_hip_d2", "complex_hip_d4", "cross_gable_d2", "cross_gable_d4", "dutch_gable_d2", "dutch_gable_d4", "flat_d2",
           "flat_d4", "flat_pitched_d2", "flat_pitched_d4", "flat_pitched_step_d2", "flat_pitched_step_d4", "gable_d2", "gable_d4",
           "hip_d2", "l_shape_d2", "l_shape_d4", "shed_d2", "shed_d4", "t_shape_d2", "two_level_d2", "two_level_d4"}


def test_exactly_the_sparse_cases_are_refused_and_every_other_case_is_measured(measured):
    """Every case at 2 or 4 returns/m2 (under the 4/m2 refusal line or too thin to find planes) is refused and no other: a new
    refusal, or a roof that used to be refused and is measured now, fails here and must be looked at."""
    assert len(measured) == 105
    assert {n for n, r in measured.items() if r.refused} == REFUSED


def test_the_engine_writes_exactly_the_contract_keys_and_only_contract_edge_types(measured):
    seen: set[str] = set()
    for name, res in measured.items():
        if res.refused:
            continue
        assert tuple(res.totals) == TOTALS_KEYS, name
        seen |= {e.type for e in res.edges}
    assert seen <= set(contract_edge_types()), seen - set(contract_edge_types())
    assert {"eave", "rake", "ridge", "hip", "valley", "flat_edge", "level_change", "step_flashing"} <= seen  # the cases do exercise them
    assert set(contract_edge_types()) <= set(VALID_EDGE_TYPES) and set(STEP_EDGE_TYPES) <= set(contract_edge_types())
    assert all(f"`{t}`" in section("model.facets, edges, objects") for t in contract_edge_types())


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


def test_the_contract_quality_keys_and_reasons_are_what_engine_quality_can_write(measured):
    from test_engine_adapter import base

    from roof_measure import quality
    from roof_measure.engine import adapter, finish, signals

    head, tail = section("model.quality").split("Reasons:")
    keys = set(re.findall(r"`([a-z_0-9]+)`", head.split("`model.quality.overhang_scale`")[0])) - {"ok", "planes"}
    reasons = set(re.findall(r"`([a-z_]+)`", tail.split("`outline_shift`")[0])) - {"roof_part_missed_sqft"}
    res = next(r for r in measured.values() if not r.refused)
    model = adapter.engine_model(res, base(), 0.0)
    assert keys == set(quality.engine_quality(res, model)), keys ^ set(quality.engine_quality(res, model))
    # the reasons the code can write: the engine's closed list (signals.REASONS, a refusal's own reason aside), the low-slope reason
    # quality.py adds and the warning codes it copies; every literal appended anywhere must be one of them
    closed = (set(signals.REASONS) - {"lidar_too_sparse"}) | {"low_slope_confirm"} | set(quality.ENGINE_COPIED)
    assert reasons == closed, reasons ^ closed
    sources = "".join(Path(m.__file__).read_text() for m in (signals, finish, quality))
    used = set(re.findall(r'(?:reasons\.append|add_reason\(\w+,)\s*\(?"([a-z_]+)"', sources))
    assert used <= closed | {"lidar_too_sparse"}, used - closed


def test_the_removed_keys_of_the_contract_are_absent_from_the_envelope(measured):
    from roof_measure.envelope import build_envelope
    from roof_measure.pipeline_result import no_verification
    from roof_measure.quality import assess_engine

    removed = set(re.findall(r"`([a-z_]+)`", section("What 0.6.0 removed").split("Old to new:")[0]))
    removed -= {"pitched_area_sqft", "flat_area_sqft", "lengths_ft"}  # still model-only shape keys: named "as envelope totals"
    res = next(r for r in measured.values() if not r.refused)
    from test_engine_adapter import base

    from roof_measure.engine import adapter

    model = adapter.engine_model(res, base(), 0.0)
    env = build_envelope(model, method_used="planes", footprint_source="lariac", verification=no_verification("n"), warnings=[],
                         warning_codes=[], assessment=assess_engine(res, model))
    assert "original_totals" not in env["verification"] and "source" in env["model"]
    assert not removed & set(env["totals"]), removed & set(env["totals"])
    assert not removed & (set(env["model"]["totals"]) - {"pitched_area_sqft", "flat_area_sqft", "lengths_ft"})
    assert not {"solar", "from_planes", "hints"} & set(env["model"]["source"])


def test_every_composite_total_is_the_sum_of_the_published_parts_exactly(measured):
    checked = 0
    for name, res in measured.items():
        if res.refused:
            continue
        t = res.totals
        checked += 1
        lanterns = sum(2 * (o["size_ft"][0] + o["size_ft"][1]) for o in res.objects if o["kind"] == "lantern")
        assert t["exposed_edge_ft"] == round(t["step_flashing_ft"] + t["wall_flashing_ft"] + round(lanterns, 2), 2), name
        assert t["eave_rake_ft"] == round(t["eave_ft"] + t["rake_ft"] + t["flat_edge_ft"] + t["exposed_edge_ft"], 2), name
        assert t["ridge_hip_ft"] == round(t["ridge_ft"] + t["hip_ft"], 2), name
        assert t["area_sqft"] == round(t["roofing_pitched_sqft"] + t["roofing_flat_sqft"], 1), name
    assert checked == 83


def _no_numpy(v, path="envelope"):
    import numpy as np

    assert not isinstance(v, np.generic | np.ndarray), (path, type(v))
    assert not isinstance(v, tuple), (path, "tuple")
    if isinstance(v, dict):
        for k, x in v.items():
            assert isinstance(k, str), (path, k)
            _no_numpy(x, f"{path}.{k}")
    elif isinstance(v, list):
        for i, x in enumerate(v):
            _no_numpy(x, f"{path}[{i}]")


def test_the_envelope_is_plain_json_types_all_the_way_down():
    import json

    from roof_measure.synth_engine_envelope import engine_envelope

    env = engine_envelope()
    json.dumps(env, allow_nan=False)  # no default=: a numpy scalar would raise
    _no_numpy(env)
    assert env["model"]["objects"] and isinstance(env["model"]["quality"]["roof_part_missed_sqft"], float)
    assert all(isinstance(v, float) for o in env["model"]["objects"] for p in o["polygon"] for v in p)
    assert all(b for b in env["model"]["blocks"]) and env["model"]["holes"] == []


def test_roof_part_missed_is_a_float_when_there_is_none(measured):
    res = next(r for r in measured.values() if not r.refused)
    assert type(res.roof_part_missed_sqft) is float
