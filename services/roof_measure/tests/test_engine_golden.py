"""The golden interface files: each stage of the engine reproduces what the next stage was built against.

Files: tests/data/engine_golden/<case>/{planes,outline,partition_summary,facets_edges}.json (synthetic roofs only).
A deliberate behaviour change regenerates them (``python -m roof_measure.engine.golden write``) and says why.
"""

import json
from pathlib import Path

import pytest

from roof_measure.engine import golden

DATA = Path(__file__).resolve().parent / "data" / "engine_golden"


@pytest.fixture(scope="module")
def runs():
    return {name: golden.run_case(name) for name in golden.GOLDEN_CASES}


def test_every_case_has_its_four_small_files():
    for name in golden.GOLDEN_CASES:
        for stem in golden.FILES:
            f = DATA / name / f"{stem}.json"
            assert f.is_file(), f
            assert f.stat().st_size < 100_000


@pytest.mark.parametrize("name", golden.GOLDEN_CASES)
@pytest.mark.parametrize("stem", golden.FILES)
def test_the_stage_reproduces_its_golden_file(runs, name, stem):
    res, st = runs[name]
    got = golden.views(res, st)[stem]
    want = json.loads((DATA / name / f"{stem}.json").read_text())
    assert golden.compare(stem, got, want) == []


def test_the_comparison_notices_a_changed_stage(runs):
    res, st = runs["gable_d8"]
    want = json.loads((DATA / "gable_d8" / "planes.json").read_text())
    got = golden.views(res, st)["planes"]
    got["planes"][0]["a"] += 0.1
    assert golden.compare("planes", got, want)
    got2 = golden.views(res, st)["facets_edges"]
    got2["facets"].pop()
    assert golden.compare("facets_edges", got2, json.loads((DATA / "gable_d8" / "facets_edges.json").read_text()))


def test_the_golden_files_hold_no_geographic_data():
    for f in DATA.rglob("*.json"):
        text = f.read_text()
        assert not any(k in text.lower() for k in ('"lat"', '"lng"', '"lon"', "epsg", '"crs"')), f
