# roof_measure

Python service: address -> footprint + LiDAR (+ Solar) -> `bond.roof_model/0.1` JSON.

## Setup

```
make setup     # uses uv, creates .venv (Python 3.12), installs the package with dev extras
make test
```

`roof-measure` is not on your PATH. Run it as `.venv/bin/roof-measure ...`, or first
`source .venv/bin/activate`. The commands below assume one of the two.

## Data layer

Address -> footprint -> LiDAR -> height-continuous roof blocks. Every data source is keyless.

| Module | Job |
|---|---|
| `geocode.py` | US Census geocoder: `geocode(address) -> Geocoded`. The point is in the street, never point-in-polygon on a parcel. |
| `footprint.py` | `fetch_footprint(lat, lng, address)`: LA County parcels within 60 m, best situs match, largest LARIAC 2020 building on it (OSM Overpass fallback). |
| `lidar.py` | `select_project` ranks USGS 3DEP EPT projects covering the point (newest year, then density); `fetch_points` reads only the octree nodes under a box; `fetch_best_points` falls through to older surveys. |
| `frame.py` | `Frame`: metric CRS (UTM zone from longitude) to feet, origin at the SW corner of the footprint bbox. |
| `blocks.py` | `segment_blocks(points, footprint_m, frame) -> BlockSet`; `to_json` writes schema `bond.roof_blocks/0.1`; `save_debug_png`. |
| `cache.py` | Disk cache under `cache/` (gitignored) keyed by sha256 of the request; `cache.stats.requests` counts real network calls. `ROOF_MEASURE_CACHE` overrides the directory. |

Block method: 0.25 m robust height raster inside the footprint, a local plane fit per cell (flat below
4 degrees, otherwise a 45-degree aspect sector, crease cells dropped), connected components with
height steps under 0.12 m using ABSOLUTE z (the ground falls 3 m across the sample site), polygons
snapped to the footprint, one plane fit per block. Blocks smaller than 3.5 m2 survive only when they
touch the footprint outline (awnings); smaller interior fragments merge into neighbours.

Cache: the first run for an address downloads about 14 MB (mostly the LiDAR project boundary
list, cached 30 days); a repeat run makes no network requests.

Tests: `make test` is offline. Recorded property data (point clouds, parcel, census and Overpass responses) lives in
`local/test-data/` and the real site config in `local/sites.json` (copy `tests/sites.example.json`); both are untracked and
tests that need them skip when absent. The point clouds are npz files saved without the `.npz` extension (`site1_roof.pts`). Live checks: `ROOF_MEASURE_NETWORK=1 .venv/bin/python -m pytest -m network`.

### Data layer: limits and behaviour

- **Call sequence:** `geocode` -> `fetch_footprint(lat, lng, geocoded.parts)` -> `Frame.for_footprint(polygon)` ->
  `lidar.fetch_for_footprint(footprint_m, frame.epsg)` (box = footprint bbox + 15 m each side) -> `segment_blocks`.
- **Errors you should expect:** `GeocodeError`, `FootprintError`, `LidarError`, `LidarTooSparse` (under 8 roof
  points/m2 inside the footprint; the message names project, year and density) and `BlocksError`. Nothing returns an
  empty block set silently. `Footprint.match` is `exact | street | nearest` and `warnings` explains a weak match.
- **Overhang:** blocks may extend `min(0.6 m, 0.08 * sqrt(footprint m2))` beyond the outline (recorded as
  `extra.overhang_m`); `plan_area_in_footprint_sqft` is the part inside the outline. A cell counts as roof only when a
  LiDAR return lies within `max(0.15, 1.4/sqrt(density))` m, so no area is invented.
- **Steep roofs:** cell tilt is accepted up to 60 degrees and the height-continuity step scales with slope.
- **Known limit, complex roofs:** a roof with many small hip wings is over-segmented. 14811 S Denker Ave, Gardena
  (2,484 sq ft footprint) returns 20 blocks in 4 aspect families, because same-aspect pieces are separated by
  differently-facing pieces and are not coplanar-adjacent, so merging cannot join them. See
  `out/gardena_14811_blocks_debug.png`. The model layer or the agent has to reconcile such blocks.
- **Known limits, awnings and canopy:** awnings lying mostly outside the county outline (site 1, x 112-123 ft) are
  not recovered at the 0.6 m overhang, and cells under tree canopy are dropped, so coverage can be well under 100%
  (site 1 78%). That 78% is the share of footprint cells the data layer assigned to a block before gap fill; the CLI's "5.2% not covered" warning is the footprint area the final model's blocks do not cover after gap fill, so the two numbers measure different things.

## Model layer

Blocks (or Solar evidence) -> roof blocks -> `bond.roof_model/0.1` JSON (`docs/contracts/roof_model.md`).

| Module | Job |
|---|---|
| `skeleton.py` | Straight skeleton (`compas_cgal`, CGAL, GPL: fine server-side). `hip_roof_edges`, `shed_roof_edges`, `block_geometry`, agent tools `measure`, `split_footprint`, `rect_fit`. Exact against the closed form (tests). |
| `classify.py` | `BlockSet` (the `bond.roof_blocks/0.1` file), `classify_blocks` / `build_roof_blocks`: awnings, hip/gable/shed from aspect clusters, footprint tiling (Voronoi gap fill), flat merge. Thresholds are constants at the top. |
| `model.py` | `build_model` (facets, typed edges, totals, confidence), `validate` (every contract rule), `write_model`. One builder for every method. |
| `solar.py` | `fetch_building_insights` (live, `SolarUnavailable` with the enable URL), `load_fixture`, `segments_to_evidence`, `evidence_to_blockset`. |
| `agent.py` | Claude tool-use loop (`claude-sonnet-5-5`, 12 round cap) deciding form, pitch source and gable edges. Never writes a number. |
| `render.py` | Debug PNG with the contract palette. |
| `cli.py`, `api.py` | `roof-measure measure ...`; FastAPI on :8011. |
| `synth.py` | Closed-form fixtures and the hand-crafted site 1 blocks. Not part of the pipeline. |

```
.venv/bin/roof-measure measure "100 Example Ave, Sampletown, CA 90000" --out out/ --blocks ../../fixtures/site1_blocks.json
.venv/bin/roof-measure measure "..." --method solar_agent --solar-fixture ../../fixtures/solar_site1_fixture.json --out out/
.venv/bin/roof-measure measure "..." --method solar_agent --solar-fixture ... --no-agent      # rules only, no key
make serve   # POST /measure {"address","method"}, GET /fixtures, GET /fixtures/{name}
.venv/bin/python -m roof_measure.synth      # regenerate the four model fixtures from fixtures/site1_blocks.json
```

`python -m roof_measure.synth` OVERWRITES `fixtures/synthetic_*.json` in the repo (relative to the
repo root, not to `services/roof_measure`). Check `git diff fixtures/` afterwards.

`POST /measure` results are cached as `out/api_<key>.json` under `services/roof_measure/out/`, where
the key is a hash of address, method, blocks path, Solar fixture and the no-agent flag. A repeated
request returns that file. The response body is the roof model itself. `method: "fixture"` returns a
saved fixture and writes nothing.

Methods: `lidar_skeleton` (rules on LiDAR blocks), `lidar_agent` (Claude decides form from the block
table), `solar_agent` (Claude decides form from Solar segments placed on the footprint). `--no-agent`
runs the rules on the same evidence. The agent needs `ANTHROPIC_API_KEY`; it is capped at 12 tool
rounds and its transcript is written to `out/agent_transcript.json`.

How edges are typed (contract section 3), by comparing roof levels either side of a block boundary:
flat beside flat at the same level is one `eave`; the lower block beside a step over 1 ft gets
`wall_flashing` (flat) or `step_flashing` (sloped); a flat block's outline edge is `parapet`.
Levels come from the LiDAR block heights (absolute z), so they are only as good as the block file.

Known limits: parapet and wall heights are not measured (rule based); flat blocks whose level
differs by under 0.5 ft merge only with `--merge-flats` (default off, so the shared lines stay as
Roofr's internal flat-to-flat eaves); Solar is disabled on our project, so the
live Solar path is untested and only the synthetic fixture has run.

Tests: `make test` (the live agent test is skipped without `ANTHROPIC_API_KEY`).

### How the numbers compare to Roofr (sample building, real blocks, 2026-11-07)

| Item | Roofr | Ours | Why the gap |
|---|---|---|---|
| Total area (sq ft) | 5,405 | 6,761 | The county outline is 6,900 sq ft; Roofr omits about 1,500 of it. Ours also counts the roof overhang past the wall line. |
| Pitched (sq ft) | 1,200 | 1,190 | Close: hip rectangle 33.4 x 30.2 ft against about 35 x 26, plus one 124 sq ft awning (Roofr has three, 255 sq ft). |
| Flat (sq ft) | 4,205 | 5,571 | Whole outline minus the hip and the awning, as above. |
| Eave (ft) | 209.7 | 203.3 | Close: hip perimeter, the awning bottom and the internal flat-to-flat lines. |
| Hip (ft) | 76.2 | 87.7 | Follows the larger hip rectangle. |
| Ridge (ft) | 7.8 | 3.1 | Near-square rectangle gives a short ridge. |
| Rake (ft) | 32 | 26.1 | The awning's two sides; Roofr draws three awnings. |
| Step flashing (ft) | 50 | 10.0 | The one awning's top edge. Roofr's other runs are not visible in LiDAR. |
| Wall flashing (ft) | 344.4 | 0 | Not derivable: LiDAR resolves no wall steps, and the 17 skylight/curb openings (about 232 ft) are not modelled. |
| Parapet (ft) | 423.8 | 417.2 | Rule: every flat outline edge. Heights are not measured. |

Hip block fitted 33.4 x 30.2 ft (1,009 sq ft plan); Roofr's hip faces sum to 948 sq ft sloped, ours 1,060.

Totals are not tuned to match Roofr; they are what the geometry gives. The model's `confidence.notes`
repeat the wall flashing and overhang caveats.
