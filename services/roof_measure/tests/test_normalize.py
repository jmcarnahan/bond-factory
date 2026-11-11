"""Address normalisation and the result-cache key (plan D4)."""

import pytest

from roof_measure.normalize import cache_key, normalize_address

BASE = {"method": "auto", "verify": True, "pipeline_version": "0.2.0", "solar_key": False, "anthropic_key": False}


@pytest.mark.parametrize("raw,want", [
    ("100 Example Ave, Sampletown, CA, 90000", "100 EXAMPLE AVE, SAMPLETOWN, CA, 90000"),
    ("100  example   ave ,sampletown, ca,  90000-1234", "100 EXAMPLE AVE,SAMPLETOWN, CA, 90000"),
    ("100 EXAMPLE AVE APT 4B, SAMPLETOWN, CA, 90000", "100 EXAMPLE AVE, SAMPLETOWN, CA, 90000"),
    ("100 EXAMPLE AVE UNIT 12, SAMPLETOWN, CA, 90000", "100 EXAMPLE AVE, SAMPLETOWN, CA, 90000"),
    ("100 EXAMPLE AVE STE 200, SAMPLETOWN, CA, 90000", "100 EXAMPLE AVE, SAMPLETOWN, CA, 90000"),
    ("100 EXAMPLE AVE SUITE B, SAMPLETOWN, CA, 90000", "100 EXAMPLE AVE, SAMPLETOWN, CA, 90000"),
    ("100 EXAMPLE AVE #5, SAMPLETOWN, CA, 90000", "100 EXAMPLE AVE, SAMPLETOWN, CA, 90000"),
    ("100 EXAMPLE AVE # 5, SAMPLETOWN, CA, 90000", "100 EXAMPLE AVE, SAMPLETOWN, CA, 90000"),
    ("", ""),
])
def test_normalize_address(raw, want):
    assert normalize_address(raw) == want


def test_unit_tokens_inside_words_are_kept():
    assert normalize_address("1 SUITEVIEW RD, X, CA, 90000").startswith("1 SUITEVIEW RD")
    assert normalize_address("5 UNITY ST, X, CA, 90000").startswith("5 UNITY ST")


def test_same_building_same_key_across_spellings():
    a = cache_key(normalized_address=normalize_address("100 Example Ave Apt 2, Sampletown, CA, 90000-0001"),
                  lat=None, lng=None, **BASE)
    b = cache_key(normalized_address=normalize_address("100 EXAMPLE AVE, SAMPLETOWN, CA, 90000"),
                  lat=None, lng=None, **BASE)
    assert a == b and len(a) == 64


def test_latlng_key_rounds_to_five_decimals():
    y, x = 10.0, 20.0
    k1 = cache_key(normalized_address=None, lat=y + 0.000001, lng=x + 0.000004, **BASE)
    k2 = cache_key(normalized_address=None, lat=y, lng=x, **BASE)
    k3 = cache_key(normalized_address=None, lat=y + 0.00002, lng=x, **BASE)
    assert k1 == k2 != k3


@pytest.mark.parametrize("change", [{"method": "lidar_skeleton"}, {"verify": False}, {"pipeline_version": "0.3.0"},
                                    {"solar_key": True}, {"anthropic_key": True}])
def test_every_output_changing_input_changes_the_key(change):
    base = cache_key(normalized_address="A", lat=None, lng=None, **BASE)
    assert cache_key(normalized_address="A", lat=None, lng=None, **(BASE | change)) != base


def test_address_and_coordinates_never_collide_and_one_is_required():
    assert cache_key(normalized_address="A", lat=1.0, lng=2.0, **BASE) == cache_key(
        normalized_address="A", lat=None, lng=None, **BASE)  # a geocoded address wins over coordinates
    with pytest.raises(ValueError):
        cache_key(normalized_address=None, lat=None, lng=None, **BASE)


def test_saint_prefixed_streets_and_unit_look_alikes_are_not_stripped():
    ste_marie = normalize_address("100 STE MARIE ST, X, CA, 90000")
    ste_anne = normalize_address("100 STE ANNE ST, X, CA, 90000")
    assert ste_marie != ste_anne and "MARIE" in ste_marie and "ANNE" in ste_anne
    assert normalize_address("1 APT ST, X, CA, 90000") == "1 APT ST, X, CA, 90000"
    assert normalize_address("1 UNIT RD, X, CA, 90000") == "1 UNIT RD, X, CA, 90000"


@pytest.mark.parametrize("raw", ["100 EXAMPLE AVE APT 2B, X, CA, 90000", "100 EXAMPLE AVE STE 400, X, CA, 90000",
                                 "100 EXAMPLE AVE UNIT B, X, CA, 90000", "100 EXAMPLE AVE, APT REAR, X, CA, 90000",
                                 "100 EXAMPLE AVE # 5, X, CA, 90000", "100 EXAMPLE AVE #5B, X, CA, 90000"])
def test_clear_unit_designators_are_stripped(raw):
    assert normalize_address(raw) == "100 EXAMPLE AVE, X, CA, 90000"


def test_negative_zero_keys_like_zero():
    a = cache_key(normalized_address=None, lat=-0.0, lng=0.0, **BASE)
    b = cache_key(normalized_address=None, lat=0.0, lng=-0.0, **BASE)
    tiny = 0.000001
    c = cache_key(normalized_address=None, lat=-tiny, lng=tiny, **BASE)
    assert a == b == c
