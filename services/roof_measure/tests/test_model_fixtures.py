"""Fixtures are real build_model outputs with closed-form totals; the CLI writes all three files."""

import json
import math

import pytest
from conftest import FIXTURES
from sites import PLACEHOLDER

from roof_measure.cli import main
from roof_measure.model import validate

NAMES = ["synthetic_hip", "synthetic_gable", "synthetic_flat_parapet", "site1_lidar"]


def load(name):
    return json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.mark.parametrize("name", NAMES)
def test_fixture_validates(name):
    validate(load(name))


def test_synthetic_hip_closed_form():
    s = 4 / 12
    t = load("synthetic_hip")["totals"]
    assert t["total_area_sqft"] == pytest.approx(35 * 26 * math.sqrt(1 + s * s), abs=0.1)
    L = t["lengths_ft"]
    assert L["eave"] == pytest.approx(122.0, abs=0.01) and L["ridge"] == pytest.approx(9.0, abs=0.01)
    assert L["hip"] == pytest.approx(4 * math.hypot(13 * math.sqrt(2), s * 13), abs=0.01)
    assert t["predominant_pitch_rise"] == 4.0


def test_synthetic_gable_closed_form():
    sf = math.sqrt(1.25)
    t = load("synthetic_gable")["totals"]
    L = t["lengths_ft"]
    assert t["total_area_sqft"] == pytest.approx(40 * 24 * sf, abs=0.1)
    assert (L["eave"], L["ridge"]) == (pytest.approx(80, abs=0.01), pytest.approx(40, abs=0.01))
    assert L["rake"] == pytest.approx(4 * 12 * sf, abs=0.01)


def test_synthetic_flat_closed_form():
    t = load("synthetic_flat_parapet")["totals"]
    assert t["total_area_sqft"] == pytest.approx(2400, abs=0.1) and t["flat_area_sqft"] == pytest.approx(2400, abs=0.1)
    assert t["lengths_ft"]["parapet"] == pytest.approx(200, abs=0.01)
    assert sum(t["lengths_ft"].values()) == pytest.approx(200, abs=0.01)
    m = load("synthetic_flat_parapet")
    assert {e["type"] for e in m["edges"]} == {"parapet"} and len(m["edges"]) == 4


def test_cli_blocks_path_writes_all_three_files(tmp_path, capsys, site1_blocks_path):
    rc = main(["measure", f"{PLACEHOLDER['line1']}, {PLACEHOLDER['city']}, {PLACEHOLDER['state']} {PLACEHOLDER['zip']}", "--out", str(tmp_path),
               "--blocks", str(site1_blocks_path)])
    assert rc == 0
    names = sorted(p.name for p in tmp_path.iterdir())
    assert [n.rsplit("_", 1)[1] for n in names] == ["blocks.json", "model.json", "model.png"]
    out = capsys.readouterr().out
    assert "Total area" in out and "Parapet" in out
    model = json.loads(next(tmp_path.glob("*_model.json")).read_text())
    validate(model)
    assert model["source"]["method"] == "lidar_skeleton"


def test_cli_data_errors_exit_nonzero_with_one_line(tmp_path, capsys, monkeypatch):
    from roof_measure import geocode

    def boom(_addr):
        raise geocode.GeocodeError("no match\nfor this address")

    monkeypatch.setattr(geocode, "geocode", boom)
    assert main(["measure", "nowhere", "--out", str(tmp_path)]) == 2
    err = capsys.readouterr().err.strip().splitlines()
    assert len(err) == 1 and err[0].startswith("error: GeocodeError: no match for this address")


def test_cli_blocks_error_and_request_errors_exit_2(tmp_path, capsys, monkeypatch):
    import requests

    from roof_measure import cli
    from roof_measure.blocks import BlocksError

    for exc in (BlocksError("No roof block survived segmentation"), requests.ConnectionError("down")):
        def boom(*a, _e=exc, **k):
            raise _e

        monkeypatch.setattr(cli, "run_pipeline", boom)
        assert main(["measure", "x", "--out", str(tmp_path)]) == 2
        assert capsys.readouterr().err.startswith("error: ")
