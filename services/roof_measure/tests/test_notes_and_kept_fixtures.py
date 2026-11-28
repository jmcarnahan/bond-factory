"""What the deleted block-path test files also covered and the plane path still does: the address label parser, the
low-density warning threshold, and that the roof model files the Dart tests read stay valid and documented."""

import json

import pytest
from conftest import FIXTURES, ROOT

from roof_measure import pipeline
from roof_measure.envelope import WARNING_CODES
from roof_measure.model import validate
from roof_measure.pipeline_notes import collect_warnings


def test_parse_address_label():
    a = pipeline.parse_address("100 Example Ave, Sampletown, CA 90000")
    assert (a.line1, a.city, a.state, a.zip) == ("100 Example Ave", "Sampletown", "CA", "90000")
    assert pipeline.parse_address("just a label").line1 == "just a label"


def test_low_density_warning_threshold_is_8_and_hard_floor_is_4():
    from roof_measure import lidar

    assert lidar.MIN_ROOF_DENSITY == 4.0
    fp = {"codes": [], "warnings": [], "other_buildings": 0}
    for density, warned in ((7.7, True), (8.0, False), (12.0, False), (None, False)):
        _, c = collect_warnings({"warnings": []}, fp, density)
        assert ("low_point_density" in c) is warned, density


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("synthetic_*.json")), ids=lambda p: p.stem)
def test_every_kept_synthetic_model_passes_validate(path):
    doc = json.loads(path.read_text())
    if doc.get("schema", "").startswith("bond.roof_model/"):
        validate(doc)


def test_docs_embed_the_pass_envelope_verbatim_and_name_every_warning_code():
    doc = (ROOT / "docs" / "contract-0.2.md").read_text()
    assert (FIXTURES / "roof_measurement_0.2_pass.json").read_text().rstrip("\n") in doc
    for code in WARNING_CODES:
        assert f"`{code}`" in doc


def test_pipeline_version_and_the_contract_name():
    from roof_measure.version import CONTRACT, PIPELINE_VERSION

    assert PIPELINE_VERSION == "0.5.1" and CONTRACT == "bond.roof_model/0.2"
