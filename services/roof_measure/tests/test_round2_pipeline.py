"""Review round: deadlines reach every fetch, transient failures are retryable, fallbacks, logs, render, verdict order."""

import json
import logging
from types import SimpleNamespace as NS

import anthropic
import httpx
import pytest
import requests
from conftest import FIXTURES

from roof_measure import cache, geocode, lidar, pipeline, solar
from roof_measure.agent import AgentError, run_agent
from roof_measure.classify import BlockSet
from roof_measure.deadline import Deadline, DeadlineExceeded
from roof_measure.envelope import cap_verification
from roof_measure.errors import code_for, error_from
from roof_measure.footprint_types import FootprintUnavailable
from roof_measure.lidar import LidarError, LidarUnavailable
from roof_measure.pipeline_notes import collect_warnings

BLOCKS = FIXTURES / "site1_blocks.json"


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


def _rate_limit():
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.RateLimitError("rate limited", response=httpx.Response(429, request=req), body=None)


@pytest.mark.parametrize("exc", [
    _rate_limit(), anthropic.APIConnectionError(request=httpx.Request("POST", "https://x")),
    anthropic.APITimeoutError(request=httpx.Request("POST", "https://x")), httpx.ConnectError("down"),
    httpx.ReadTimeout("slow"), solar.SolarUnavailable("Solar API returned HTTP 503."),
    solar.SolarUnavailable("Solar API request failed (ConnectionError); key not shown."),
    AgentError("Anthropic API error: HTTP 529 overloaded"), pipeline.PipelineError("The agent failed: HTTP 429 x"),
])
def test_transient_upstream_errors_are_retryable(exc):
    assert code_for(exc) == "upstream_unavailable" and error_from(exc)["retryable"] is True


def test_wrapped_sdk_rate_limit_is_found_through_the_cause_chain():
    try:
        try:
            raise _rate_limit()
        except anthropic.APIError:
            raise AgentError("Anthropic API error: rate limited") from None  # `from None` still keeps __context__
    except AgentError as exc:
        assert code_for(exc) == "upstream_unavailable"
    assert code_for(solar.SolarUnavailable("The Solar API is not enabled or this key is not allowed (HTTP 403)")) == (
        "measurement_failed")


def test_solar_body_that_is_not_json_is_solar_unavailable(monkeypatch):
    class R:
        status_code, ok = 200, True

        def json(self):
            raise ValueError("no json")

    monkeypatch.setattr(solar.requests, "get", lambda *a, **k: R())
    with pytest.raises(solar.SolarUnavailable, match="not JSON"):
        solar.fetch_building_insights(1.0, 2.0, "key")


def test_agent_gets_a_per_call_timeout_and_checks_the_deadline():
    bs = BlockSet.load(BLOCKS)
    ev = solar.segments_to_evidence(solar.load_fixture(FIXTURES / "synthetic_solar_response.json"), bs.frame,
                                    bs.footprint_ft)
    seen = []

    class Client:
        messages = NS(create=lambda **kw: seen.append(kw) or (_ for _ in ()).throw(AgentError("stop")))

    with pytest.raises(AgentError):
        run_agent(bs, ev, kind="solar", client=Client(), deadline=Deadline.after(100))
    assert 0 < seen[0]["timeout"] <= 30
    with pytest.raises(DeadlineExceeded):
        run_agent(bs, ev, kind="solar", client=Client(), deadline=Deadline.after(0))
    assert len(seen) == 1


def test_pipeline_binds_the_deadline_to_every_fetch(tmp_path, net):
    with pytest.raises(DeadlineExceeded):
        pipeline.run_pipeline("100 Example Ave, Sampletown, CA 90000", tmp_path, "lidar_skeleton",
                              deadline=Deadline.after(0))
    assert net == []


def test_auto_fallback_failure_reraises_the_lidar_error_with_a_note(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("GOOGLE_SOLAR_API_KEY", "k")
    sparse = lidar.LidarTooSparse("P", 2020, 3.0, 4.0)

    def fake_run(address, out_dir, method, **kw):
        raise sparse if method == "lidar_skeleton" else RuntimeError("solar down")

    monkeypatch.setattr(pipeline, "_run", fake_run)
    with pytest.raises(lidar.LidarTooSparse) as e:
        pipeline.run_pipeline("x", tmp_path, "auto")
    assert e.value is sparse and code_for(e.value) == "lidar_too_sparse"
    msg = error_from(e.value)["message"]
    assert "3.0 points/m2" in msg and "solar_agent fallback also failed" in msg


def test_auto_does_not_fall_back_on_lidar_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("GOOGLE_SOLAR_API_KEY", "k")
    seen = []

    def fake_run(address, out_dir, method, **kw):
        seen.append(method)
        raise LidarUnavailable("Could not list USGS 3DEP projects (HTTP 503).")

    monkeypatch.setattr(pipeline, "_run", fake_run)
    with pytest.raises(LidarUnavailable):
        pipeline.run_pipeline("x", tmp_path, "auto")
    assert seen == ["lidar_skeleton"]


def test_a_render_failure_adds_a_warning_instead_of_failing(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def boom(*a, **k):
        raise RuntimeError("matplotlib exploded")

    monkeypatch.setattr(pipeline, "render_png", boom)
    res = pipeline.run_pipeline("x", tmp_path, "lidar_skeleton", blocks_path=BLOCKS)
    assert "png" not in res.paths and "The debug picture could not be rendered." in res.envelope["warnings"]
    assert len(res.envelope["warnings"]) == len(res.envelope["warning_codes"])


def test_render_uses_no_pyplot_state(tmp_path):
    import re
    from pathlib import Path

    from roof_measure import render

    model = json.loads((FIXTURES / "synthetic_hip.json").read_text())
    for _ in range(3):
        render.render_png(model, tmp_path / "m.png")
    assert (tmp_path / "m.png").stat().st_size > 1000
    assert not re.search(r"^\s*(import|from) matplotlib\.pyplot", Path(render.__file__).read_text(), re.MULTILINE)


def test_the_degraded_verdict_is_final_before_warnings_so_the_code_lands():
    ver = {"verdict": "pass", "notes": []}
    capped = cap_verification(ver, "solar")
    assert capped["verdict"] == "adjusted" and ver["verdict"] == "pass"
    assert cap_verification(capped, "solar") == capped  # idempotent
    fp = {"codes": ["footprint_solar"], "warnings": ["s"], "other_buildings": 0}
    _, codes = collect_warnings({"warnings": []}, fp, capped, 20.0, None, "lidar_skeleton")
    assert "verifier_adjusted" in codes
    _, codes = collect_warnings({"warnings": []}, fp, ver, 20.0, None, "lidar_skeleton")
    assert "verifier_adjusted" not in codes


def test_pipeline_emits_verifier_adjusted_for_a_pass_on_a_solar_footprint(tmp_path, monkeypatch):
    doc = json.loads(BLOCKS.read_text())
    doc["extra"] = {**doc.get("extra", {}), "_fp": {"source": "solar", "warnings": ["from solar"],
                                                      "codes": ["footprint_solar"], "other_buildings": 0}}
    path = tmp_path / "blocks.json"
    path.write_text(json.dumps(doc))
    monkeypatch.setattr(pipeline, "_verify", lambda model, *a: (model, {
        "verdict": "pass", "notes": [], "adjustments": [], "original_totals": {}, "model": None, "rounds": 0,
        "usage": {"input_tokens": 0, "output_tokens": 0}}, []))
    res = pipeline.run_pipeline("x", tmp_path / "out", "lidar_skeleton", blocks_path=path)
    assert res.footprint_source == "solar" and res.envelope["verification"]["verdict"] == "adjusted"
    assert "verifier_adjusted" in res.envelope["warning_codes"] and "footprint_solar" in res.envelope["warning_codes"]


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


def test_render_false_skips_the_picture_without_a_warning(tmp_path):
    res = pipeline.run_pipeline("x", tmp_path / "off", "lidar_skeleton", blocks_path=BLOCKS, render=False)
    assert "png" not in res.paths and not list((tmp_path / "off").glob("*.png"))
    assert "png" not in res.model["debug"]
    assert not any("debug picture" in w for w in res.envelope["warnings"])


def test_render_true_writes_the_picture(tmp_path):
    res = pipeline.run_pipeline("x", tmp_path / "on", "lidar_skeleton", blocks_path=BLOCKS)
    assert res.paths["png"].is_file() and res.model["debug"]["png"] == res.paths["png"].name
    assert json.loads(res.paths["model"].read_text())["debug"]["png"] == res.paths["png"].name  # written after render


def test_a_missing_matplotlib_skips_the_picture_without_a_warning(tmp_path, monkeypatch):
    import sys

    import roof_measure

    for name in ("matplotlib", "matplotlib.figure", "matplotlib.lines", "matplotlib.patches",
                 "matplotlib.backends", "matplotlib.backends.backend_agg"):
        monkeypatch.setitem(sys.modules, name, None)
    monkeypatch.delitem(sys.modules, "roof_measure.render", raising=False)
    monkeypatch.delattr(roof_measure, "render", raising=False)
    res = pipeline.run_pipeline("x", tmp_path, "lidar_skeleton", blocks_path=BLOCKS)
    assert "png" not in res.paths and not list(tmp_path.glob("*.png"))
    assert not any("debug picture" in w for w in res.envelope["warnings"])
    written = json.loads(next(tmp_path.glob("*_model.json")).read_text())
    assert "png" not in written["debug"] and "png" not in res.model["debug"]
