# roof_measure

Python library: address -> footprint + USGS 3DEP LiDAR -> the plane engine -> a roof measurement envelope
`bond.roof_model/0.2` (`bond.roof_model/0.1` model inside), pipeline 0.7.0. Apps call `roof_measure.measure()` in-process.
Roof model, totals and call: [docs/contract-0.7.md](../../docs/contract-0.7.md) (older shapes: [0.2](../../docs/contract-0.2.md),
[0.3](../../docs/contract-0.3.md), [0.4](../../docs/contract-0.4.md)). Licence: see the repository `NOTICE`.

## Use as a library

`make setup` installs `.[dev,render]` for development. A consumer installs only the core (numpy, scipy, shapely, pyproj,
laspy, requests); pin a full SHA, see [contract §3.1](../../docs/contract-0.2.md).

```python
from roof_measure import measure, MeasureError

try:
    envelope = measure("100 Example Ave, Sampletown, CA 90000", cache_dir="/var/cache/roof", on_stage=print)
except MeasureError as e:          # e.code, e.message, e.retryable
    print(e.to_dict())
```

This geocodes and downloads LiDAR, so it needs the network and a writable `cache_dir`. For an offline try-out pass
`points_path="<house folder>"` (`points_wide.npy`, `footprint.json`, `meta.json`: the regression set's layout).
`measure()` blocks for up to `deadline_s + 30` s: run it off the request thread. `engine`, `method`, `hints`, `verify`,
`anthropic_api_key` and `google_solar_api_key` are gone (a caller that passes one gets a `TypeError`).

## Pipeline

`library.py` (child process, `_isolate.py`/`_child.py`) -> `pipeline.py` -> `pipeline_engine.py` -> `engine/` -> `envelope.py`.

1. Geocode (`geocode.py`, Census) unless `lat` and `lng` are given.
2. Footprint (`footprint.py` chain, each link records `footprint_source`): LA County parcel + LARIAC
   (`footprint_county.py`, `lariac`), OpenStreetMap (`footprint_osm.py`, `osm`), a hull of the LiDAR roof surface
   (`footprint_hull.py`, `lidar_hull`; caps confidence at 0.5, never `pass`).
3. LiDAR (`lidar.py`, EPT over HTTPS): the roof returns of the building.
4. The plane engine (`engine/`): facets from the measured planes, flat and pitched told apart at 2/12, typed edges,
   the things standing on the roof (`engine/objects.py`: chimneys, lanterns), one set of totals (`engine/totals.py`) and quality signals; `engine/adapter.py` makes the model, `quality.py` the quality object.
5. Envelope (`envelope.py`): totals, confidence, warning codes. No verifier runs: the verification block says `unverified`,
   `skipped: engine`.

`include_other_buildings=True` measures the other county outlines of the parcel with the same engine (`lot.py`).
`deadline.py` is the shared time budget (footprint stage capped at 60 s).

| Module | Job |
|---|---|
| `geocode.py` | US Census geocoder. The point is in the street: never point-in-polygon on a parcel. |
| `lidar.py` | `select_project` ranks 3DEP EPT projects covering the point; `fetch_best_points` falls through to older surveys; under 4 roof points/m2 is `LidarTooSparse`, under 8 adds a `low_point_density` warning. |
| `frame.py` | Metric CRS (UTM zone from longitude) to feet, origin at the south-west corner of the footprint box. |
| `cache.py` | Disk cache of every HTTP body, keyed by request, 30 day TTL. |

Tests are offline and use synthetic roofs; recorded property data lives in the untracked `local/test-data/` and the real
site list in `local/sites.json` (see `tests/sites.example.json`). Tests that need them skip when absent. Live checks:
`ROOF_MEASURE_NETWORK=1 .venv/bin/python -m pytest -m network`.

## Commands

```
make test                      # offline suite
make lint
make fixtures                  # regenerate ../../fixtures/roof_engine/roof_measurement_0.7_engine.json (the engine's example envelope)
make roof-eval / roof-synth    # the regression harness, tools/roof_eval/README.md
```
