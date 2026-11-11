"""Exception class -> API error code, and the error object shape."""

import pytest
import requests

from roof_measure import cache
from roof_measure.blocks import BlocksError
from roof_measure.deadline import DeadlineExceeded
from roof_measure.errors import JOB_CODES, REQUEST_CODES, code_for, error_body, error_object, retryable_for
from roof_measure.footprint_types import AmbiguousBuilding, FootprintError
from roof_measure.geocode import GeocodeError
from roof_measure.lidar import LidarError, LidarTooSparse
from roof_measure.model import ModelError
from roof_measure.pipeline import PipelineError
from roof_measure.solar import SolarUnavailable


@pytest.mark.parametrize("exc,code", [
    (GeocodeError("The Census geocoder found no match for 'x'."), "address_not_found"),
    (GeocodeError("The Census geocoder could not be reached (boom)."), "upstream_unavailable"),
    (FootprintError("No building footprint found near x."), "no_footprint"),
    (FootprintError("OpenStreetMap (Overpass) could not be reached, so no fallback."), "upstream_unavailable"),
    (AmbiguousBuilding("two buildings"), "ambiguous_building"),
    (LidarError("No USGS 3DEP LiDAR project covers this address."), "no_lidar_coverage"),
    (LidarError("Could not list USGS 3DEP projects (timed out)."), "upstream_unavailable"),
    (LidarTooSparse("P", 2020, 3.0, 8.0), "lidar_too_sparse"),
    (BlocksError("No roof block survived"), "measurement_failed"),
    (ModelError("bad"), "measurement_failed"),
    (PipelineError("agent failed"), "measurement_failed"),
    (SolarUnavailable("disabled"), "measurement_failed"),
    (cache.BadResponse("not json"), "upstream_unavailable"),
    (requests.ConnectionError("down"), "upstream_unavailable"),
    (requests.Timeout("slow"), "upstream_unavailable"),
    (DeadlineExceeded("lidar"), "timeout"),
    (TimeoutError("t"), "timeout"),
    (RuntimeError("anything else"), "measurement_failed"),
    (KeyError("x"), "measurement_failed"),
])
def test_code_for(exc, code):
    assert code_for(exc) == code


def test_every_job_code_is_reachable_or_set_elsewhere():
    reached = {code_for(e) for e in (GeocodeError("none"), FootprintError("none"), AmbiguousBuilding("x"),
                                     LidarError("none"), LidarTooSparse("P", 1, 1.0, 8.0), RuntimeError("x"),
                                     requests.ConnectionError("x"), DeadlineExceeded("s"))}
    assert reached == set(JOB_CODES) - {"interrupted"}  # interrupted is set by the boot scan, not an exception


def test_retryable_set():
    assert {c for c in [*REQUEST_CODES, *JOB_CODES] if retryable_for(c)} == {
        "queue_full", "upstream_unavailable", "timeout", "interrupted"}


def test_error_object_shape_and_no_exception_text_leaks():
    obj = error_object("no_footprint")
    assert set(obj) == {"code", "message", "retryable"} and obj["retryable"] is False
    assert error_body("timeout") == {"error": {"code": "timeout", "message": "The measurement took too long; retry later.",
                                               "retryable": True}}
    assert "secret" not in str(error_object(code_for(RuntimeError("secret /private/path"))))


def test_pipeline_messages_are_kept_one_line_and_bounded_other_text_is_not():
    from roof_measure.errors import error_from

    obj = error_from(BlocksError("No roof block survived\nsegmentation " + "x" * 400))
    assert obj["code"] == "measurement_failed" and "\n" not in obj["message"] and len(obj["message"]) == 300
    assert obj["message"].startswith("No roof block survived segmentation")
    assert error_from(RuntimeError("secret /private/path"))["message"] == "The roof could not be measured."
