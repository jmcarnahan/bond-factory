"""Edge classification rules (contract section 3) on toy block sets."""

import pytest

from roof_measure.classify import BlockSet, RoofBlock
from roof_measure.model import ModelError, build_model, validate

RING = [(0, 0), (40, 0), (40, 20), (0, 20)]


def _bs(ring=RING):
    return BlockSet(address={"formatted": "toy"}, origin={"lat": 0, "lng": 0}, frame={}, footprint_ft=ring,
                    footprint_meta={"provider": "t", "id": "1", "area_sqft": 800.0})


def _flat(i, poly, level):
    return RoofBlock(id=f"b{i}", form="flat", polygon=poly, level_ft=level, eave_height_ft=level)


def test_internal_flat_to_flat_is_one_eave_and_outline_is_parapet():
    a = _flat(1, [(0, 0), (20, 0), (20, 20), (0, 20)], 10.0)
    b = _flat(2, [(20, 0), (40, 0), (40, 20), (20, 20)], 10.0)
    m = build_model(_bs(), [a, b], {"method": "fixture"})
    L = m["totals"]["lengths_ft"]
    assert L["eave"] == pytest.approx(20.0)  # once, not twice
    assert L["parapet"] == pytest.approx(120.0)
    assert L["wall_flashing"] == 0
    internal = [e for e in m["edges"] if e["type"] == "eave"]
    assert len(internal) == 1 and len(internal[0]["facets"]) == 2


def test_flat_beside_higher_flat_is_still_an_eave():
    a = _flat(1, [(0, 0), (20, 0), (20, 20), (0, 20)], 10.0)
    b = _flat(2, [(20, 0), (40, 0), (40, 20), (20, 20)], 14.0)
    L = build_model(_bs(), [a, b], {"method": "fixture"})["totals"]["lengths_ft"]
    assert L["eave"] == pytest.approx(20.0) and L["wall_flashing"] == 0


def test_flat_beside_higher_hip_is_wall_flashing_on_the_flat():
    a = _flat(1, [(0, 0), (20, 0), (20, 20), (0, 20)], 10.0)
    hip = RoofBlock(id="b2", form="hip", polygon=[(20, 0), (40, 0), (40, 20), (20, 20)], pitch_rise=4.0,
                    level_ft=14.0, eave_height_ft=14.0)
    L = build_model(_bs(), [a, hip], {"method": "fixture"})["totals"]["lengths_ft"]
    assert L["wall_flashing"] == pytest.approx(20.0)


def test_hip_beside_higher_flat_gets_step_flashing_and_same_level_gets_eave():
    hip = RoofBlock(id="b1", form="hip", polygon=[(0, 0), (20, 0), (20, 20), (0, 20)], pitch_rise=4.0,
                    level_ft=10.0, eave_height_ft=10.0)
    high = _flat(2, [(20, 0), (40, 0), (40, 20), (20, 20)], 15.0)
    L = build_model(_bs(), [hip, high], {"method": "fixture"})["totals"]["lengths_ft"]
    assert L["step_flashing"] == pytest.approx(20.0)
    assert L["eave"] == pytest.approx(60.0)  # the other three sides of the hip
    same = _flat(2, [(20, 0), (40, 0), (40, 20), (20, 20)], 10.0)
    L2 = build_model(_bs(), [hip, same], {"method": "fixture"})["totals"]["lengths_ft"]
    assert L2["step_flashing"] == 0 and L2["eave"] == pytest.approx(80.0)


def test_shed_awning_edges():
    flat = _flat(1, [(0, 0), (40, 0), (40, 20), (0, 20)], 20.0)
    shed = RoofBlock(id="b2", form="shed", polygon=[(10, 0), (20, 0), (20, 8), (10, 8)], pitch_rise=4.0,
                     aspect_deg=180.0, level_ft=17.0, eave_height_ft=17.0)
    # shed lies inside the flat's footprint here only for the test: give the flat a hole-free ring beside it
    flat.polygon = [(0, 0), (10, 0), (10, 8), (20, 8), (20, 0), (40, 0), (40, 20), (0, 20)]
    L = build_model(_bs(), [flat, shed], {"method": "fixture"})["totals"]["lengths_ft"]
    assert L["eave"] == pytest.approx(10.0)  # low edge on the outline
    assert L["step_flashing"] == pytest.approx(10.0) and L["rake"] > 0  # top flashed, sides rakes


def test_validate_rejects_missing_lengths_key():
    m = build_model(_bs(), [_flat(1, RING, 0.0)], {"method": "fixture"})
    del m["totals"]["lengths_ft"]["valley"]
    with pytest.raises(ModelError, match="ten keys"):
        validate(m)


def test_validate_rejects_bad_edge_type_and_totals():
    m = build_model(_bs(), [_flat(1, RING, 0.0)], {"method": "fixture"})
    m["edges"][0]["type"] = "gutter"
    with pytest.raises(ModelError):
        validate(m)
    m = build_model(_bs(), [_flat(1, RING, 0.0)], {"method": "fixture"})
    m["totals"]["squares"] = 1.0
    with pytest.raises(ModelError, match="squares"):
        validate(m)


def _facet(kind, pitch, area):
    return {"kind": kind, "pitch_rise": pitch, "area_sqft": area}


def test_predominant_pitch_uses_half_step_buckets():
    from roof_measure.model import predominant_pitch

    mixed = [_facet("sloped", 3.86, 600), _facet("sloped", 4.1, 500), _facet("flat", 0.0, 900)]
    assert predominant_pitch(mixed) == (4.0, pytest.approx(1100))


def test_predominant_pitch_tie_goes_to_the_lower_pitch():
    from roof_measure.model import predominant_pitch

    assert predominant_pitch([_facet("sloped", 4.0, 500), _facet("flat", 0.0, 500)]) == (0.0, pytest.approx(500))
    assert predominant_pitch([_facet("sloped", 0.4, 100), _facet("flat", 0.0, 100)]) == (0.0, pytest.approx(200))


def test_validate_checks_predominant_bucket():
    hip = RoofBlock(id="b1", form="hip", polygon=RING, pitch_rise=3.86, level_ft=0.0, eave_height_ft=0.0)
    m = build_model(_bs(), [hip], {"method": "fixture"})
    assert m["totals"]["predominant_pitch_rise"] == 4.0
    m["totals"]["predominant_pitch_rise"] = 3.86
    with pytest.raises(ModelError, match="bucket"):
        validate(m)
