"""Street-line normalisation and its use in the parcel match (synthetic addresses only)."""

from __future__ import annotations

import pytest

from roof_measure import footprint_county
from roof_measure.geocode import Address
from roof_measure.street_names import normalize_street, same_street, street_key


@pytest.mark.parametrize("a,b", [
    ("100 Example Ave", "100 EXAMPLE AVENUE"),
    ("100 Ave B", "100 AVENUE B"),
    ("100 ave b.", "100 Avenue B"),
    ("7 Oak St.", "7 OAK STREET"),
    ("7 Oak Dr", "7 Oak Drive"),
    ("7 Oak Blvd", "7 OAK BOULEVARD"),
    ("7 Oak Rd", "7 oak road"),
    ("7 Oak Ln", "7 OAK LANE"),
    ("7 Oak Ct", "7 OAK COURT"),
    ("7 Oak Pl", "7 OAK PLACE"),
    ("7 Oak Ter", "7 OAK TERRACE"),
    ("7 Oak Cir", "7 OAK CIRCLE"),
    ("7 Oak Pkwy", "7 OAK PARKWAY"),
    ("7 Oak Hwy", "7 OAK HIGHWAY"),
    ("7 Oak Trl", "7 OAK TRAIL"),
    ("7 Oak Sq", "7 OAK SQUARE"),
    ("7   Oak   St", "7 Oak St"),
    ("20 W 182nd St", "20 WEST 182ND STREET"),
    ("20 Main St NW", "20 MAIN STREET NORTHWEST"),
    ("20 N Main St", "20 NORTH MAIN STREET"),
    ("20 First St", "20 1st St"),
    ("20 Tenth Ave", "20 10TH AVENUE"),
    ("20 Oak St Apt 5", "20 Oak Street"),
    ("20 Oak St Unit B", "20 Oak Street"),
    ("20 Oak St #5", "20 Oak Street"),
    ("20 Oak St, Ste 200", "20 Oak Street"),
    ("20 Oak St # 5", "20 Oak Street"),
])
def test_abbreviation_only_differences_normalise_equal(a, b):
    assert normalize_street(a) == normalize_street(b)


def test_ave_h_the_letter_is_the_name_not_a_unit():
    assert normalize_street("12 Ave B") == "12 AVENUE B"
    assert normalize_street("12 Avenue B") == "12 AVENUE B"
    assert normalize_street("12 Ave C") != normalize_street("12 Ave B")


def test_a_street_called_n_is_not_north():
    assert normalize_street("100 N St") == "100 N STREET"
    assert normalize_street("10 N St") != normalize_street("10 North St")
    assert normalize_street("10 North St") == "10 NORTH STREET"
    assert normalize_street("100 N St") != normalize_street("100 St")


def test_leading_st_is_saint_not_street():
    assert normalize_street("5 St Andrews Pl") == "5 SAINT ANDREWS PLACE"
    assert normalize_street("5 Saint Andrews Pl") == "5 SAINT ANDREWS PLACE"
    assert "STREET" not in normalize_street("5 St Andrews Pl")


def test_fraction_stays_in_the_house_number():
    assert normalize_street("12 1/2 Ave B") == "12 1/2 AVENUE B"
    assert normalize_street("12 1/2 Ave B") != normalize_street("12 Ave B")
    assert street_key("12 1/2 Ave B") == "AVENUE B"


def test_spanish_prefixes_stay():
    assert normalize_street("12 Avenida del Sol") == "12 AVENIDA DEL SOL"
    assert normalize_street("12 Calle Real") == "12 CALLE REAL"
    assert normalize_street("12 Camino Real") == "12 CAMINO REAL"
    assert normalize_street("12 Via Verde") == "12 VIA VERDE"


def test_punctuation_case_and_empty():
    assert normalize_street("") == ""
    assert normalize_street("  12   O'Brien   St. ") == "12 O BRIEN STREET"
    assert normalize_street("St") == "STREET"


def test_different_streets_stay_different():
    assert normalize_street("10 Oak St") != normalize_street("10 Elm St")
    assert normalize_street("10 Oak St") != normalize_street("11 Oak St")
    assert normalize_street("10 Oak St") != normalize_street("10 Oak Dr")


def test_same_street_tolerances():
    assert same_street(street_key("1418 W 182nd St"), street_key("182ND STREET"))  # direction missing on one side
    assert not same_street(street_key("1 N Main St"), street_key("1 S Main St"))
    assert same_street(street_key("1 Oak"), street_key("1 Oak Street"))  # type missing on one side
    assert not same_street(street_key("1 Oak Dr"), street_key("1 Oak Street"))
    assert not same_street("", "")


# ---- use in the parcel score -------------------------------------------------------------------------------------

def _props(house="100", street="EXAMPLE AVENUE", direction=" "):
    return {"SitusHouseNo": house, "SitusStreet": street, "SitusDirection": direction,
            "SitusAddress": f"{house} {street}", "AIN": "1"}


def _addr(line):
    return Address(line, "Sampletown", "CA", "90000")


def test_abbreviation_only_difference_scores_as_exact():
    assert footprint_county.score_parcel(_props(), _addr("100 Example Ave")) >= 8
    assert footprint_county.score_parcel(_props(street="AVENUE B"), _addr("100 Ave B")) >= 8


def test_direction_in_its_own_situs_field_still_matches():
    assert footprint_county.score_parcel(_props(street="182ND ST", direction="W"), _addr("100 W 182nd St")) >= 8


def test_different_number_or_name_is_not_exact():
    assert footprint_county.score_parcel(_props(house="102"), _addr("100 Example Ave")) < 8
    assert footprint_county.score_parcel(_props(), _addr("10 Other Ave")) < 8
    assert footprint_county.score_parcel(_props(street="AVENUE C"), _addr("100 Ave B")) < 8
    assert footprint_county.score_parcel(_props(street="EXAMPLE DRIVE"), _addr("100 Example Ave")) < 8


def test_pick_parcel_abbreviation_is_exact_without_warning_text():
    feats = [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[(0, 0), (1, 0), (1, 1), (0, 0)]]},
              "properties": _props(street="AVENUE B")}]
    _, match = footprint_county.pick_parcel(feats, 0.5, 0.5, _addr("100 Ave B"))
    assert match == "exact"
