"""Review round: deadlines reach every fetch, transient failures are retryable, fallbacks, logs, render, verdict order."""

import logging

import pytest
import requests

from roof_measure import cache, geocode, lidar, pipeline
from roof_measure.deadline import Deadline, DeadlineExceeded
from roof_measure.envelope import cap_verification
from roof_measure.errors import code_for, error_from
from roof_measure.footprint_types import FootprintUnavailable
from roof_measure.lidar import LidarError, LidarUnavailable


@pytest.fixture
def net(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOF_MEASURE_CACHE", str(tmp_path / "cache"))
    seen = []

    def send(method, url, params, data, headers, timeout):
        seen.append({"url": url, "timeout": timeout})
        raise requests.ConnectionError(f"boom {url} {params}")

    monkeypatch.setattr(cache, "_send", send)
    monkeypatch.setattr(cache.time, "sleep", lambda s: None)
    return seen


def test_fetch_honours_the_deadline_cap_retries_and_expiry(net):
    with pytest.raises(requests.ConnectionError):
        cache.fetch_bytes("https://x.test/a", deadline=Deadline.after(5), timeout=60, retries=2)
    assert len(net) == 2 and all(c["timeout"] <= 5 for c in net)  # one retry at most, timeout capped by the time left
    net.clear()
    with pytest.raises(DeadlineExceeded):
        cache.fetch_bytes("https://x.test/b", deadline=Deadline.after(0))
    assert net == []  # not even attempted
    net.clear()
    with pytest.raises(requests.ConnectionError):
        cache.fetch_bytes("https://x.test/c", retries=2)
    assert len(net) == 3  # no deadline: unchanged behaviour


def test_ambient_deadline_scope_covers_nested_fetches_and_threads(net):
    import contextvars
    from concurrent.futures import ThreadPoolExecutor

    with cache.deadline_scope(Deadline.after(0)):
        with pytest.raises(DeadlineExceeded):
            cache.fetch_json("https://x.test/d")
        ctx = contextvars.copy_context()
        with ThreadPoolExecutor(1) as pool, pytest.raises(DeadlineExceeded):
            pool.submit(ctx.run, cache.fetch_json, "https://x.test/e").result()
    assert net == []
    with pytest.raises(requests.ConnectionError):  # the scope ended
        cache.fetch_json("https://x.test/f", retries=0)


def test_geocode_failure_never_puts_the_address_in_logs_or_the_message(net, caplog):
    caplog.set_level(logging.DEBUG)
    with pytest.raises(geocode.GeocodeError) as e:
        geocode.geocode("100 Example Ave, Sampletown, CA 90000")
    assert "Example" not in caplog.text and "Example" not in str(e.value) and "ConnectionError" in str(e.value)
    assert code_for(e.value) == "upstream_unavailable"


def test_lidar_outage_is_unavailable_not_no_coverage(monkeypatch):
    def boom(lat, lng):
        raise requests.ConnectionError("503")

    monkeypatch.setattr(lidar, "select_project", boom)
    with pytest.raises(LidarUnavailable) as e:
        lidar.fetch_best_points(34.0, -118.0, 30, 32611, footprint_m=None)
    assert code_for(e.value) == "upstream_unavailable" and error_from(e.value)["retryable"] is True
    monkeypatch.setattr(lidar, "select_project", lambda lat, lng: [lidar.LidarProject("p", "u", 2020, 1.0, 1.0)])

    def fail(*a):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(lidar, "fetch_points", fail)
    with pytest.raises(LidarUnavailable):  # every project failed on the network
        lidar.fetch_best_points(34.0, -118.0, 30, 32611, footprint_m=None)
    monkeypatch.setattr(lidar, "select_project", lambda lat, lng: [])
    with pytest.raises(LidarError) as e2:
        lidar.fetch_best_points(34.0, -118.0, 30, 32611, footprint_m=None)
    assert not isinstance(e2.value, LidarUnavailable) and code_for(e2.value) == "no_lidar_coverage"


def test_footprint_unavailable_is_retryable():
    assert code_for(FootprintUnavailable("OpenStreetMap (Overpass) could not be reached")) == "upstream_unavailable"


@pytest.mark.parametrize("exc", [
    requests.ReadTimeout("slow"), requests.ConnectTimeout("down"), pipeline.PipelineError("The step failed: HTTP 429 x"),
])
def test_transient_upstream_errors_are_retryable(exc):
    assert code_for(exc) == "upstream_unavailable" and error_from(exc)["retryable"] is True


def test_pipeline_binds_the_deadline_to_every_fetch(tmp_path, net):
    with pytest.raises(DeadlineExceeded):
        pipeline.run_pipeline("100 Example Ave, Sampletown, CA 90000", tmp_path, "lidar_skeleton",
                              deadline=Deadline.after(0))
    assert net == []


def test_a_degraded_footprint_lowers_pass_to_adjusted():
    ver = {"verdict": "pass", "notes": []}
    capped = cap_verification(ver, "lidar_hull")
    assert capped["verdict"] == "adjusted" and ver["verdict"] == "pass"
    assert cap_verification(capped, "lidar_hull") == capped  # idempotent


def test_bad_data_while_listing_projects_is_permanent_not_an_outage(monkeypatch):
    for exc in (ValueError("not json"), KeyError("features")):
        monkeypatch.setattr(lidar, "select_project", lambda lat, lng, e=exc: (_ for _ in ()).throw(e))
        with pytest.raises(LidarError) as e:
            lidar.fetch_best_points(34.0, -118.0, 30, 32611, footprint_m=None)
        assert not isinstance(e.value, LidarUnavailable) and code_for(e.value) == "no_lidar_coverage"
    monkeypatch.setattr(lidar, "select_project", lambda lat, lng: [lidar.LidarProject("p", "u", 2020, 1.0, 1.0)])
    monkeypatch.setattr(lidar, "fetch_points", lambda *a: (_ for _ in ()).throw(ValueError("garbled tile")))
    with pytest.raises(LidarError) as e2:  # every project failed on bad data, not on the network
        lidar.fetch_best_points(34.0, -118.0, 30, 32611, footprint_m=None)
    assert not isinstance(e2.value, LidarUnavailable)
