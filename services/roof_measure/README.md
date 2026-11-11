# roof_measure

Private Python service: address -> footprint + USGS 3DEP LiDAR (+ Google Solar, + an LLM verifier) -> a roof
measurement envelope `bond.roof_model/0.2` (`bond.roof_model/0.1` model inside), behind an async job API.
Apps call it over HTTP only; the straight skeleton uses CGAL through compas_cgal (GPL), so the code is not
linked into any app. API and envelope: [docs/contract-0.2.md](../../docs/contract-0.2.md).

## Run locally

```
make setup
ROOF_MEASURE_AUTH=off ROOF_MEASURE_HOST=127.0.0.1 ROOF_MEASURE_DEBUG=1 make serve   # same defaults as plain `make serve`
curl -s localhost:8011/healthz
curl -s -X POST localhost:8011/v1/measurements -H 'content-type: application/json' \
  -d '{"address": "100 Example Ave, Sampletown, CA 90000", "method": "fixture"}'      # debug fixture job, no network
curl -s localhost:8011/v1/measurements/<id>
```

Auth is on unless `ROOF_MEASURE_AUTH=off` AND the bind host is loopback. Without `ROOF_MEASURE_TOKEN` (32+
characters) the process refuses to start. Debug fixture routes and request fields exist only with
`ROOF_MEASURE_DEBUG=1`. Environment variables: [contract Appendix A](../../docs/contract-0.2.md).

## Docker and Railway

Build context is the repository root (uv workspace lock, shared fixtures):

```
docker buildx build --platform linux/amd64 -f services/roof_measure/Dockerfile -t roof-measure .
docker run --rm -p 8011:8011 -e ROOF_MEASURE_HOST=0.0.0.0 -e ROOF_MEASURE_TOKEN=<32+ chars> -v roof-data:/data roof-measure
```

The image binds `::` by default, which uvicorn opens IPv6-only. Railway's proxy and private network are IPv6, so
that stays the default there. A local `docker run -p` maps over IPv4 and never reaches it, so local Docker testing
needs `-e ROOF_MEASURE_HOST=0.0.0.0`. The start-up log line prints the bind host. The slim image has no curl or
ps: Railway runs the `/healthz` check over HTTP from outside, so nothing in the container needs them.

The image runs as a non-root user and keeps jobs, results and the fetch cache under `/data`. On Railway use one
replica, a volume mounted at `/data`, `ROOF_MEASURE_TOKEN`, and optionally `ANTHROPIC_API_KEY` (verifier, agent
methods) and `GOOGLE_SOLAR_API_KEY` (Solar footprint link). `railway.toml` sets the `/healthz` health check. `RAILWAY_RUN_UID=0` is
required on the service: the volume mounts root-owned, so the container must run as root to create `/data/jobs`
(without it the service logs the fix and stops at boot). Size the volume for about 5 GB: results are a few KB
each, finished job directories (PNG, blocks, transcripts) go after 14 days, and the fetch cache (LiDAR tiles, several
MB per building) is purged after 30 days.

## Pipeline

`api.py` (routes) -> `service.py` (cache or queue) -> `jobs.py` (disk job store, bounded worker pool) ->
`runner.py` (geocode, result cache) -> `pipeline.py` -> `envelope.py`.

1. Geocode (`geocode.py`, Census) unless `lat` and `lng` are given.
2. Footprint (`footprint.py` chain, each link records `footprint_source`): LA County parcel + LARIAC
   (`footprint_county.py`, `lariac`), OpenStreetMap with three hedged Overpass mirrors (`footprint_osm.py`, `osm`),
   Google Solar segment boxes when a key is set (`footprint_solar.py`, `solar`), a hull of the LiDAR roof
   surface (`footprint_hull.py`, `lidar_hull`). Solar and hull footprints cap confidence at 0.5 and never `pass`.
3. LiDAR (`lidar.py`, EPT over HTTPS) -> height-continuous blocks (`blocks.py`) -> classification
   (`classify.py`, `skeleton.py`) or an agent (`agent.py`) -> model (`model.py`).
4. Verifier (`verify*.py`): deterministic merge of tiny collinear segments, then an LLM review when
   `ANTHROPIC_API_KEY` is set. It never fails a job; trouble means verdict `unverified`.
5. Envelope: 14 totals including the drip edge and ridge cap variants, confidence, warning codes.

`method: "auto"`: LiDAR skeleton; when LiDAR is missing or too sparse and both the Solar and Anthropic keys are
set, `solar_agent`; otherwise the job fails with the LiDAR error code. `deadline.py` is the shared time budget
(`ROOF_MEASURE_JOB_TIMEOUT_S`, footprint stage capped at 60 s).

Each job writes under `DATA_DIR/jobs/<id>/`: `job.json`, `result.json`, `<tag>_blocks.json`, `<tag>_model.json`,
`<tag>_model.png`, agent and verifier transcripts. Results for repeat requests are in `DATA_DIR/results/`.

## Data layer notes

| Module | Job |
|---|---|
| `geocode.py` | US Census geocoder. The point is in the street: never point-in-polygon on a parcel. |
| `lidar.py` | `select_project` ranks 3DEP EPT projects covering the point; `fetch_best_points` falls through to older surveys; under 4 roof points/m2 is `LidarTooSparse`, under 8 adds a `low_point_density` warning. |
| `frame.py` | Metric CRS (UTM zone from longitude) to feet, origin at the south-west corner of the footprint box. |
| `blocks.py` | 0.25 m height raster in the footprint, local plane fits, connected components with steps under 0.12 m, polygons snapped to the footprint. |
| `cache.py` | Disk cache of every HTTP body, keyed by request, 30 day TTL, `ROOF_MEASURE_CACHE` overrides the directory. |

Blocks may extend a little past the outline (roof overhang), so areas can exceed the footprint area. Wall and parapet
heights are not measured; parapets are rule based. Tests are offline; recorded property data lives in the untracked
`local/test-data/` and the real site list in `local/sites.json` (see `tests/sites.example.json`). Tests that need them
skip when absent. Live checks: `ROOF_MEASURE_NETWORK=1 .venv/bin/python -m pytest -m network`.

## Commands

```
make test                      # offline suite
make lint
make fixtures                  # regenerate ../../fixtures synthetic models and the four 0.2 envelopes
.venv/bin/roof-measure measure "100 Example Ave, Sampletown, CA 90000" --out out/ --blocks ../../fixtures/site1_blocks.json
.venv/bin/python -m roof_measure.synth      # regenerate the closed-form 0.1 fixtures (overwrites ../../fixtures/synthetic_*.json)
```

Methods: `lidar_skeleton` (rules), `lidar_agent` (Claude picks forms from the block table), `solar_agent` (Claude
picks forms from Solar segments). `--no-agent` runs the rules on the same evidence. The agent is capped at 12
tool rounds.
