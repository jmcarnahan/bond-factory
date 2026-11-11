"""Shared paths and site fixtures for the tests."""

from pathlib import Path

import pytest
from sites import load_site, local_data_path

from roof_measure import cache, footprint
from roof_measure.footprint_types import FootprintError

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "fixtures"
DATA = Path(__file__).resolve().parent / "data"


@pytest.fixture(scope="session")
def site1() -> dict:
    """The real site 1 config from local/sites.json; skips when it is not present."""
    site = load_site("site1")
    if site is None:
        pytest.skip("local/sites.json missing; see tests/sites.example.json")
    return site


@pytest.fixture
def local_data():
    """`local_data("x")` returns the path of local/test-data/x, or skips the test."""
    def _get(name: str) -> Path:
        path = local_data_path(name)
        if path is None:
            pytest.skip(f"local/test-data/{name} missing")
        return path
    return _get


@pytest.fixture(scope="session")
def site1_blocks_path() -> Path:
    path = FIXTURES / "site1_blocks.json"
    assert path.is_file(), "run `python -m roof_measure.synth --site1-blocks` first"
    return path


@pytest.fixture(scope="session")
def solar_fixture_path() -> Path:
    path = FIXTURES / "synthetic_solar_response.json"
    assert path.is_file(), "run `make fixtures` first"
    return path


@pytest.fixture(scope="session")
def handmade_blocks_path() -> Path:
    """Hand-crafted blocks (hip + 3 awnings + 4 flats); regenerate with `python -m roof_measure.synth --site1-blocks`."""
    path = DATA / "site1_blocks_handmade.json"
    assert path.is_file()
    return path


class Net:
    """Routes cache.fetch_json by URL fragment; a value can be a dict, an exception, or a callable."""

    def __init__(self):
        self.routes, self.calls = {}, []

    def __call__(self, url, **kw):
        self.calls.append((url, kw))
        for frag, val in self.routes.items():
            if frag in url:
                if callable(val):
                    return val(url, kw)
                if isinstance(val, Exception):
                    raise val
                return val
        raise AssertionError(f"unexpected request {url}")

    def urls(self):
        return [u for u, _ in self.calls]


@pytest.fixture
def net(monkeypatch):
    n = Net()
    monkeypatch.setattr(cache, "fetch_json", n)
    monkeypatch.delenv("GOOGLE_SOLAR_API_KEY", raising=False)
    monkeypatch.setattr(footprint, "fetch_hull", lambda *a, **k: (_ for _ in ()).throw(FootprintError("no lidar")))
    return n


