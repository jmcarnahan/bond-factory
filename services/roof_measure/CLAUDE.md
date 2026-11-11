# roof_measure

Role: private async job API. Address -> footprint chain + LiDAR (+ Solar, + LLM verifier) -> envelope
`bond.roof_model/0.2` (model `bond.roof_model/0.1`). Python 3.12, FastAPI, port $PORT (8011). The one deployed
module: Dockerfile (context = repo root), railway.toml. Contract: docs/contract-0.2.md, docs/contracts/roof_model.md.

## Key files (roof_measure/)
- api.py routes only; service.py cache-or-queue; jobs.py disk job store + worker pool; runner.py job body
- auth.py bearer + start-up refusal; errors.py code_for(exc); settings.py env; keys.py/normalize.py cache keys
- pipeline.py run_pipeline (deadline, lat_lng, on_stage, verify, auto); cli.py CLI; envelope.py 0.2 result
- footprint.py chain; footprint_{county,osm,solar,hull}.py links; footprint_types.py Footprint
- verify*.py verifier (own seam); deadline.py shared time budget; version.py PIPELINE_VERSION
- geocode, lidar, blocks, classify (859 lines), skeleton, agent, model, render, solar, cache: the pipeline
- synth*.py fixture generators (not pipeline); `make fixtures` rewrites ../../fixtures

## Commands (this dir)
- `make setup` once; `make test`; one file `.venv/bin/pytest tests/test_x.py`; `make lint`; `make fixtures`; `make serve`

## Rules
- New code in new modules; split over-cap files (classify, blocks, model, agent, lidar, skeleton) when touched.
- Docker binds `::` (IPv6-only): local `docker run -p` needs ROOF_MEASURE_HOST=0.0.0.0. Env: contract Appendix A.
- Deadlines: cache.fetch_bytes reads the ambient cache.deadline_scope (runner, pipeline); watchdog = deadline + 30 s.
- Never log token or address at INFO; never read tests/data/**, local/test-data/*.pts, uv.lock. Real sites: local/sites.json only; tests needing them skip; network tests need ROOF_MEASURE_NETWORK=1.
- cache/, out/, data/ are gitignored.
- Known limits: small or oddly segmented roofs can fail at blocks (measurement_failed); `lidar_agent` is the manual retry.
