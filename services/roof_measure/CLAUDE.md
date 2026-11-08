# roof_measure

Role: address -> footprint + LiDAR (+ Solar, optional Claude agent) -> roof model JSON `bond.roof_model/0.1`.
Python 3.12, FastAPI on :8011. Contract: docs/contracts/roof_model.md. Reads ../../fixtures.

## Key files (pipeline order, in roof_measure/)
- geocode.py — address to lat/lng (Census geocoder)
- footprint.py — building footprint
- lidar.py — USGS 3DEP point cloud over HTTPS (EPT)
- solar.py — Google Solar API evidence rows (optional)
- frame.py — coordinate frame shared by every stage
- blocks.py — height-continuous roof blocks from LiDAR + footprint
- classify.py — blocks to form, polygon, pitch (859 lines: split when next touched)
- skeleton.py — straight-skeleton geometry for hip, gable, shed
- agent.py — optional Claude agent choosing the roof form per part
- model.py — blocks to the contract JSON
- render.py — debug PNG of a model; synth.py — synthetic fixtures (not pipeline)
- cli.py — CLI + pipeline entry; api.py — HTTP API for the demo; cache.py — fetch cache

## Commands (from this dir)
- Once: `make setup`
- All tests: `make test`
- One file: `.venv/bin/pytest tests/test_model_classify.py` (Makefile has no T=)
- Lint: `make lint`; serve: `make serve`; run: `make measure ADDR="..."`

## Rules
- Real site config is `local/sites.json` (copy `tests/sites.example.json`); property data is in `local/test-data/`.
- Tests that need them skip when absent (a fresh clone still passes).
- Network tests are marked `network`; they run only with `ROOF_MEASURE_NETWORK=1`.
- Never read `local/test-data/*.pts`. Never read uv.lock.
- cache/ and out/ are gitignored; do not commit them.
- The uv workspace root holds uv.lock; add deps in pyproject.toml, then lock at the root.
- `anthropic` is needed only for the agent track.
