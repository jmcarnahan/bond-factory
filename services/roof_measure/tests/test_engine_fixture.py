"""The engine example envelope cannot go stale: ``make fixtures`` output equals the committed file, byte for byte, and the
keys that move with the code (engine parameters hash, jump, verifier shape) are what the code emits today."""

from __future__ import annotations

import json

from conftest import FIXTURES

from roof_measure import synth_envelopes
from roof_measure.engine.params import DEFAULT
from roof_measure.synth_envelopes import ENGINE_DIR, ENGINE_NAME

PATH = FIXTURES / ENGINE_DIR / f"{ENGINE_NAME}.json"


def test_the_committed_engine_example_is_what_the_generator_writes_now(tmp_path):
    synth_envelopes.generate_all(tmp_path)
    fresh = (tmp_path / ENGINE_DIR / f"{ENGINE_NAME}.json").read_bytes()
    assert fresh == PATH.read_bytes(), "run `make fixtures` in services/roof_measure and commit fixtures/roof_engine"


def test_the_example_carries_the_contract_04_keys_with_current_values():
    env = json.loads(PATH.read_text())
    m = env["model"]
    assert m["source"]["engine"] == "planes/1" and m["source"]["engine_params"] == DEFAULT.stable_hash()
    assert env["verification"]["skipped"] == "engine" and env["verification"]["verdict"] == "unverified"
    assert "verifier_unverified" not in env["warning_codes"]
    jumps = [e["jump_ft"] for e in m["edges"] if e["type"] == "level_change"]
    assert jumps and all(j > 0.3 / 0.3048 for j in jumps)
    assert m["quality"]["engine"] == "planes/1" and set(m["totals"]["lengths_ft"]) >= {"flat_edge", "level_change"}
    assert env["totals"]["roofing_flat_sqft"] > 0 and env["totals"]["roofing_pitched_sqft"] > 0


def test_the_example_origin_projects_back_to_its_frame_origin():
    from pyproj import Transformer

    env = json.loads(PATH.read_text())
    o = env["model"]["origin"]
    x, y = Transformer.from_crs(4326, o["epsg"], always_xy=True).transform(o["lng"], o["lat"])
    # the example's frame origin is the placeholder spot lat 0, lng 0 in its zone (synth_engine_envelope)
    x0, y0 = Transformer.from_crs(4326, 32631, always_xy=True).transform(0.0, 0.0)
    assert o["epsg"] == 32631 and abs(x - x0) < 0.01 and abs(y - y0) < 0.01
