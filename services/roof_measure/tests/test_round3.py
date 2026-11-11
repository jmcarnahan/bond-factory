"""Final review round: outage results are not cached, stuck-worker accounting, cleanup and lidar nits, messages."""

import os
import time
from types import SimpleNamespace as NS

import pytest
import requests
from fastapi.testclient import TestClient
from test_footprint_chain import ADDR, LAT, LNG, D, building, osm_way, parcel
from test_jobs_api import ENVELOPE, Runs, wait

from roof_measure import api, footprint, footprint_osm, footprint_solar, lidar, pipeline
from roof_measure.errors import code_for
from roof_measure.footprint_types import FootprintError, FootprintUnavailable
from roof_measure.jobs import JobRunner, JobStore
from roof_measure.model_cleanup import _dedupe, clean_facets
from roof_measure.settings import Settings

TOKEN = "t" * 32
BODY = {"address": "100 Example Ave, Sampletown, CA 90000", "lat": 1.5, "lng": 2.5}


def make(tmp_path, run=None, **kw):
    app = api.create_app(Settings(data_dir=tmp_path, debug=True, **kw), token=TOKEN, run=run)
    return TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}, raise_server_exceptions=False)


# ---- NW1 / S1: an outage fall-through is flagged transient and never cached
def osm_ok(net):
    for u in footprint_osm.OVERPASS_URLS:
        net.routes[u] = {"elements": [osm_way(7)]}


def test_county_down_then_osm_is_transient_and_a_clean_run_is_not(net):
    net.routes["LACounty_Parcel"] = requests.ConnectionError("down")
    osm_ok(net)
    fp = footprint.fetch_footprint(LAT, LNG, ADDR)
    assert fp.source == "osm" and fp.transient is True
    net.routes["LACounty_Parcel"] = {"features": []}  # outside the county layer: a miss, not an outage
    assert footprint.fetch_footprint(LAT, LNG, ADDR).transient is False
    net.routes["LACounty_Parcel"] = {"features": [parcel()]}
    net.routes["Countywide_Building_Outlines"] = {"features": [building()]}
    assert footprint.fetch_footprint(LAT, LNG, ADDR).transient is False


def test_osm_down_then_hull_is_transient(net, monkeypatch):
    from shapely.geometry import box

    from roof_measure.footprint_types import Footprint

    net.routes["LACounty_Parcel"] = {"features": []}
    for u in footprint_osm.OVERPASS_URLS:
        net.routes[u] = requests.ConnectionError("down")
    hull = Footprint(provider="lidar_hull", id="h", polygon_wgs84=box(LNG, LAT, LNG + D, LAT + D), height_ft=1.0,
                     area_sqft=1.0, parcel_id=None, source="lidar_hull")
    monkeypatch.setattr(footprint, "fetch_hull", lambda *a, **k: hull)
    assert footprint.fetch_footprint(LAT, LNG, ADDR).transient is True


def test_every_link_down_including_county_and_solar_is_upstream_unavailable(net, monkeypatch):
    net.routes["LACounty_Parcel"] = requests.ConnectionError("down")
    for u in footprint_osm.OVERPASS_URLS:
        net.routes[u] = {"elements": []}
    monkeypatch.setenv("GOOGLE_SOLAR_API_KEY", "k")
    monkeypatch.setattr(footprint_solar.solar, "fetch_building_insights",
                        lambda *a, **k: (_ for _ in ()).throw(footprint_solar.solar.SolarUnavailable("HTTP 503.")))
    monkeypatch.setattr(footprint, "fetch_hull", lambda *a, **k: (_ for _ in ()).throw(FootprintError("none")))
    with pytest.raises(FootprintUnavailable) as e:
        footprint.fetch_footprint(LAT, LNG, ADDR)
    assert code_for(e.value) == "upstream_unavailable" and "LA County" in str(e.value)


def test_solar_outage_is_unavailable_but_solar_disabled_is_a_miss(monkeypatch):
    def raises(msg):
        return lambda *a, **k: (_ for _ in ()).throw(footprint_solar.solar.SolarUnavailable(msg))

    monkeypatch.setattr(footprint_solar.solar, "fetch_building_insights", raises("Solar API returned HTTP 503."))
    with pytest.raises(FootprintUnavailable):
        footprint_solar.fetch_solar(LAT, LNG, "k")
    monkeypatch.setattr(footprint_solar.solar, "fetch_building_insights", raises("not enabled (HTTP 403: x)"))
    assert footprint_solar.fetch_solar(LAT, LNG, "k") is None


def test_outage_then_recovery_returns_the_fresh_result_not_the_cached_outage(tmp_path, monkeypatch):
    from roof_measure import geocode, synth_envelopes

    env = synth_envelopes.envelopes()["roof_measure_0.2_pass".replace("roof_measure", "roof_measurement")]
    calls = []

    def fake(address, out_dir, method, **kw):
        calls.append(len(calls))
        return NS(envelope={**env, "footprint_source": "osm" if len(calls) == 1 else "lariac"},
                  footprint_source="x", transient=len(calls) == 1)

    monkeypatch.setattr(pipeline, "run_pipeline", fake)
    monkeypatch.setattr(geocode, "geocode", lambda a: geocode.Geocoded(
        34.0, -118.0, "100 EXAMPLE AVE, SAMPLETOWN, CA, 90000", geocode.Address("100 Example Ave", "S", "CA", "90000")))
    c = make(tmp_path)
    first = wait(c, c.post("/v1/measurements", json={"address": "100 example ave"}).json()["id"])
    assert first["result"]["footprint_source"] == "osm" and not list(c.app.state.service.results.root.glob("*.json"))
    second = c.post("/v1/measurements", json={"address": "100 example ave"}).json()
    assert second["status"] == "queued"  # the outage result was not served from the cache
    assert wait(c, second["id"])["result"]["footprint_source"] == "lariac"
    third = c.post("/v1/measurements", json={"address": "100 example ave"}).json()
    assert third["status"] == "done"  # the good result is cached


# ---- S3: a pin never becomes the alias of a plain address
def test_a_latlng_request_does_not_write_the_address_alias(tmp_path, monkeypatch):
    from roof_measure import synth_envelopes

    env = synth_envelopes.envelopes()["roof_measurement_0.2_pass"]
    monkeypatch.setattr(pipeline, "run_pipeline", lambda *a, **k: NS(envelope=env, footprint_source="osm",
                                                                      transient=False))
    c = make(tmp_path)
    wait(c, c.post("/v1/measurements", json=BODY).json()["id"])
    plain = c.post("/v1/measurements", json={"address": BODY["address"]}).json()
    assert plain["status"] == "queued"  # not answered with whichever pin ran last
    assert not list(c.app.state.service.results.root.glob("alias_*"))


# ---- S4 / S5: purges, stuck workers
def test_caches_are_purged_hourly_after_jobs_not_only_at_boot(tmp_path, monkeypatch):
    from roof_measure import jobs

    monkeypatch.setattr(jobs, "EXTRA_PURGE_EVERY_S", 0.0)
    ran = []
    r = JobRunner(JobStore(tmp_path), 1, 1, 5.0, lambda *a: ENVELOPE, extra_purge=lambda: ran.append(1))
    j = r.store.create({"address": "x"})
    r.submit(j["id"])
    end = time.time() + 5
    while not ran and time.time() < end:
        time.sleep(0.02)
    assert ran
    monkeypatch.setattr(jobs, "EXTRA_PURGE_EVERY_S", 3600.0)
    r._last_extra_purge = time.monotonic()
    ran.clear()
    r._purge()
    assert ran == []  # rate limited
    r.shutdown()


def test_healthz_reports_abandoned_workers_and_queued_jobs_fail_when_all_are_stuck(tmp_path):
    import threading

    release = threading.Event()

    def stuck(job, out_dir, deadline, on_stage):
        release.wait(10)
        return ENVELOPE

    c = make(tmp_path, stuck, job_timeout_s=0.1, workers=1, queue_max=5)
    c.app.state.service.runner.grace_s = 0.1
    assert c.get("/healthz").json() == {"status": "ok", "pipeline_version": "0.2.0", "abandoned_workers": 0}
    a = c.post("/v1/measurements", json={**BODY, "lat": 1.0}).json()
    queued = c.post("/v1/measurements", json={**BODY, "lat": 2.0}).json()
    assert wait(c, a["id"], secs=5)["error"]["code"] == "timeout"
    assert wait(c, queued["id"], secs=5)["error"]["code"] == "timeout"  # failed, not left waiting forever
    h = c.get("/healthz").json()
    assert h["status"] == "ok" and h["abandoned_workers"] == 1
    assert c.post("/v1/measurements", json={**BODY, "lat": 3.0}).status_code == 429  # nothing could run it
    release.set()
    end = time.time() + 5
    while c.get("/healthz").json()["abandoned_workers"] and time.time() < end:
        time.sleep(0.05)
    assert c.get("/healthz").json()["abandoned_workers"] == 0


def test_a_stage_update_never_lands_on_an_abandoned_job(tmp_path):
    r = JobRunner(JobStore(tmp_path), 1, 1, 5.0, lambda *a: ENVELOPE)
    j = r.store.create({"address": "x"})
    r.store.update(j["id"], status="failed", stage=None)
    r._abandoned.add(j["id"])
    r._stage(j["id"], "lidar")
    assert r.store.get(j["id"])["stage"] is None
    r.shutdown()


def test_stray_tmp_files_are_purged(tmp_path):
    from roof_measure.results import ResultCache

    store, rc = JobStore(tmp_path), ResultCache(tmp_path)
    j = store.create({"address": "x"})
    tmp1, tmp2 = store.job_dir(j["id"]) / "a.tmp", rc.root / "b.tmp"
    for t in (tmp1, tmp2):
        t.write_text("x")
        os.utime(t, (time.time() - 7200, time.time() - 7200))
    fresh = store.job_dir(j["id"]) / "c.tmp"
    fresh.write_text("x")
    store.purge(14)
    rc.purge(14)
    assert not tmp1.exists() and not tmp2.exists() and fresh.exists()


# ---- model cleanup nits
def facet(ring, fid="f1"):
    return {"id": fid, "polygon": [list(p) for p in ring], "pitch_rise": 0.0, "plan_area_sqft": 0, "area_sqft": 0}


def test_compounded_removals_are_measured_against_the_original_area():
    # two thin spikes, each about 0.3% of the facet: one may go, both together exceed 0.5%
    ring = [(0, 0), (60, 0), (60, 40), (30.5, 40), (30, 54.4), (29.5, 40), (20.5, 40), (20, 54.4), (19.5, 40), (0, 40)]
    f = facet(ring)
    notes = clean_facets([f], [])
    assert len(notes) == 1 and len(f["polygon"]) == len(ring) - 1


def test_the_wrap_around_dedupe_resolves_chains_so_no_edge_snaps_to_a_dropped_vertex():
    ring = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.02), (0.0, 0.04)]
    out, moved = _dedupe(ring)
    assert out == ring[:4] and moved[(0.0, 0.04)] == (0.0, 0.0) and moved[(0.0, 0.02)] == (0.0, 0.0)
    edge = {"id": "e1", "type": "eave", "points": [[0.0, 0.04], [10.0, 0.0]], "facets": ["f1"], "length_ft": 10.0}
    f = facet(ring)
    edges = [edge]
    clean_facets([f], edges)
    assert edges[0]["points"][0] == [0.0, 0.0] and [0.0, 0.0] in f["polygon"]


# ---- lidar: 4xx is permanent, 5xx and 429 are outages
@pytest.mark.parametrize("status,outage", [(404, False), (403, False), (500, True), (503, True), (429, True)])
def test_a_tile_http_status_decides_permanent_or_outage(monkeypatch, status, outage):
    err = requests.HTTPError(f"{status}")
    err.response = NS(status_code=status)
    monkeypatch.setattr(lidar, "select_project", lambda lat, lng: [lidar.LidarProject("p", "u", 2020, 1.0, 1.0)])
    monkeypatch.setattr(lidar, "fetch_points", lambda *a: (_ for _ in ()).throw(err))
    with pytest.raises(lidar.LidarError) as e:
        lidar.fetch_best_points(34.0, -118.0, 30, 32611, footprint_m=None)
    assert isinstance(e.value, lidar.LidarUnavailable) is outage


# ---- 422 messages name the field; startup misconfiguration
@pytest.mark.parametrize("body,needle", [
    ({"address": "x", "lat": 1.0}, "lat requires lng"), ({"address": "x", "lng": 1.0}, "lat requires lng"),
    ({}, "address is required"), ({"address": "x", "lat": "34", "lng": 1.0}, "lat must be a number"),
    ({"address": "x", "verify": 1}, "verify must be true or false"), ({"address": "x", "bogus": 1}, "bogus is not a known"),
    ({"address": "x", "method": "bad"}, "method"), ({"address": "x", "lat": 91, "lng": 0}, "lat is above"),
    ({"address": " "}, "address must not be blank"),
])
def test_422_messages_name_the_field(tmp_path, body, needle):
    r = make(tmp_path, Runs()).post("/v1/measurements", json=body)
    assert r.status_code == 422 and needle in r.json()["error"]["message"]


def test_a_misconfigured_start_is_one_line_and_exit_1(monkeypatch, capsys):
    monkeypatch.delenv("ROOF_MEASURE_TOKEN", raising=False)
    monkeypatch.setenv("ROOF_MEASURE_TOKEN", "short")
    monkeypatch.setattr(api, "_app", None)
    with pytest.raises(SystemExit) as e:
        api.__getattr__("app")
    err = capsys.readouterr().err
    assert e.value.code == 1 and err.count("\n") == 1 and "Traceback" not in err
