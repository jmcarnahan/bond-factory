"""Runtime config: authoritative when set, environment fallback when not (library use, plan D1)."""

import contextvars
import threading
from pathlib import Path

import pytest

from roof_measure import cache, config, footprint, footprint_osm
from roof_measure.config import Runtime
from roof_measure.deadline import Deadline


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("ANTHROPIC_API_KEY", "GOOGLE_SOLAR_API_KEY", "ROOF_MEASURE_CACHE", "ROOF_MEASURE_OVERPASS_URLS"):
        monkeypatch.delenv(name, raising=False)


def test_without_a_runtime_the_helpers_read_the_environment(monkeypatch):
    assert config.current() is None
    assert config.anthropic_key() is None and config.solar_key() is None
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-a")
    monkeypatch.setenv("GOOGLE_SOLAR_API_KEY", "env-g")
    assert config.anthropic_key() == "env-a" and config.solar_key() == "env-g"
    assert config.cache_root() is None and config.overpass_urls() is None and config.footprint_stage_s() is None


def test_a_runtime_is_final_even_when_the_environment_has_keys(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-a")
    monkeypatch.setenv("GOOGLE_SOLAR_API_KEY", "env-g")
    with config.use(Runtime(cache_dir=tmp_path)):  # keys None: "no key", never the paid key in the environment
        assert config.anthropic_key() is None and config.solar_key() is None
    with config.use(Runtime(cache_dir=tmp_path, anthropic_api_key="arg-a", google_solar_api_key="arg-g")):
        assert config.anthropic_key() == "arg-a" and config.solar_key() == "arg-g"


def test_use_resets_after_the_block_and_after_an_exception(tmp_path):
    rt = Runtime(cache_dir=str(tmp_path))
    assert isinstance(rt.cache_dir, Path)
    with config.use(rt):
        assert config.current() is rt
    assert config.current() is None
    with pytest.raises(RuntimeError), config.use(rt):
        raise RuntimeError("boom")
    assert config.current() is None


def test_cache_dir_prefers_the_runtime_over_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("ROOF_MEASURE_CACHE", str(tmp_path / "env"))
    assert cache.cache_dir() == tmp_path / "env"
    with config.use(Runtime(cache_dir=tmp_path / "rt")):
        assert cache.cache_dir() == tmp_path / "rt" and (tmp_path / "rt").is_dir()


def test_mirror_urls_honours_the_runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("ROOF_MEASURE_OVERPASS_URLS", "https://env.example/api")
    assert footprint_osm.mirror_urls() == ("https://env.example/api",)
    with config.use(Runtime(cache_dir=tmp_path, overpass_urls=("https://rt.example/api",))):
        assert footprint_osm.mirror_urls() == ("https://rt.example/api",)
    with config.use(Runtime(cache_dir=tmp_path)):  # no urls in the Runtime: the defaults, never the environment
        assert footprint_osm.mirror_urls() == footprint_osm.DEFAULT_OVERPASS_URLS


def test_footprint_stage_cap_honours_the_runtime(monkeypatch, tmp_path):
    caps = []
    real = Deadline.after

    def spy(seconds):
        caps.append(seconds)
        return real(seconds)

    monkeypatch.setattr(footprint.Deadline, "after", spy)
    monkeypatch.setattr(footprint, "fetch_county", lambda *a, **k: (object(), [], None))
    with config.use(Runtime(cache_dir=tmp_path, footprint_stage_s=7.0)):
        footprint.fetch_footprint(0.0, 0.0, None)
        assert caps == [7.0]
    caps.clear()
    footprint.fetch_footprint(0.0, 0.0, None)
    assert caps == [footprint.FOOTPRINT_STAGE_S]


def test_the_contextvar_reaches_copied_contexts_but_not_plain_threads(tmp_path):
    seen = {}

    def read(name):
        seen[name] = config.current()

    with config.use(Runtime(cache_dir=tmp_path)):
        ctx = contextvars.copy_context()
        t1 = threading.Thread(target=lambda: ctx.run(read, "copied"))
        t2 = threading.Thread(target=read, args=("plain",))
        for t in (t1, t2):
            t.start()
            t.join()
    assert seen["copied"] is not None and seen["plain"] is None  # a plain Thread starts with an empty context


def test_a_runtime_without_a_stage_cap_uses_60_seconds_not_the_environment(monkeypatch, tmp_path):
    import importlib

    monkeypatch.setenv("ROOF_MEASURE_FOOTPRINT_S", "5")
    try:
        fp_mod = importlib.reload(footprint)
        assert fp_mod.FOOTPRINT_STAGE_S == 5.0
        caps = []
        real = Deadline.after
        monkeypatch.setattr(fp_mod.Deadline, "after", lambda s: caps.append(s) or real(s))
        monkeypatch.setattr(fp_mod, "fetch_county", lambda *a, **k: (object(), [], None))
        with config.use(Runtime(cache_dir=tmp_path)):
            fp_mod.fetch_footprint(0.0, 0.0, None)
        assert caps == [60.0]
        caps.clear()
        fp_mod.fetch_footprint(0.0, 0.0, None)  # no Runtime: the environment still applies
        assert caps == [5.0]
    finally:
        monkeypatch.delenv("ROOF_MEASURE_FOOTPRINT_S")
        importlib.reload(footprint)
