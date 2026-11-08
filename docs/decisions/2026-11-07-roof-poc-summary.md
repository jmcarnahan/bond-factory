# Roof measurement POC: summary (2026-11-07)

Goal: given a street address, produce Roofr-style roof diagrams (edge lengths by type, facet
areas, pitch, totals) that an app can print or attach to a job, with the drawing done by a
Dart package our Flutter apps can depend on.

Result: **yes, from free open data, for buildings in LA County.** The pipeline runs cold in
about 7 s and reproduces the shape, pitch and totals of the sample Roofr report to within a
few percent for every quantity the data can see. Two quantities Roofr prints cannot be seen in
the data (wall flashing and the openings), and one discrepancy with Roofr is unexplained.

## What was built

| Piece | Where | What it does |
|---|---|---|
| Contract | `docs/contracts/roof_model.md` | Schema `bond.roof_model/0.1`: feet, plan coordinates, blocks, facets, ten edge types, totals, confidence. The only thing that crosses the Python/Dart boundary. |
| Service | `services/roof_measure/` (Python 3.12, FastAPI on :8011) | Address → Census geocode → LA County LARIAC building outline → USGS 3DEP LiDAR (2023, ~19 pts/m²) → roof blocks (flat / hip / gable / shed, pitch per block) → CGAL straight skeleton → classified edges → model JSON + debug PNG. Also a Google Solar + Claude agent track that runs on a synthetic Solar fixture. |
| Dart core | `packages/bond_roof/` (pure Dart) | Parses the model, recomputes totals, builds the length diagram, area diagram and summary block as a Scene of primitives, exports SVG and PDF. 108 tests. |
| Flutter | `packages/bond_roof_ui/` | Draws a Scene on a Canvas, builds a two-page report, print and share through `printing`. |
| Demo | `demos/roof_demo/` (web + iOS) | Address field, method selector, Measure button (calls the service), fixture chips that work offline, inline report with Print and Save PDF. No popups. |
| Fixtures | `fixtures/` | Roofr's report hand-digitised (`site1_truth.json`), our output (`site1_lidar.json`), three closed-form synthetic roofs. |
| Research | `docs/research/2026-11-07-roof-poc/` | Per-topic findings with evidence: LiDAR coverage, footprints, plane fitting, Solar API, Dart rendering, ground truth. |

## Sample: site 1 (a real roof; address in local/sites.json, not tracked) (Roofr report vs our LiDAR run)

| | Roofr | Ours | Note |
|---|---|---|---|
| Total area, sq ft | 5,405 | 6,760 | See "Unresolved" below |
| Pitched area, sq ft | 1,200 | 1,190 | Hip 1,060 + awning 130 (Roofr: hip 948 + three awnings 255) |
| Flat area, sq ft | 4,205 | 5,570 | |
| Hip pitch | not printed (implied 4.6–5/12) | 3.86/12 | LiDAR plane fit, ±0.1/12 |
| Eave, ft | 209.7 | 203.4 | |
| Hip, ft | 76.2 | 87.7 | Our hip block is 33.4 × 30.2 ft, ~12% larger than Roofr's |
| Ridge, ft | 7.8 | 3.1 | |
| Rake, ft | 32.0 | 26.1 | |
| Step flashing, ft | 50.0 | 10.0 | Two of three awnings lost under tree canopy |
| Wall flashing, ft | 344.4 | 0 | Not derivable: LiDAR resolves no wall steps and the 17 curb openings are not modelled |
| Parapet, ft | 423.8 | 417.3 | Assigned by rule (flat edge on the outline) |

Other buildings (no Roofr reference): site 3, run live end to end, comes
out as one gable block with two facets at 3.2/12, 1,058 sq ft, eave 75.0 ft, rake 56.4 ft,
ridge 37.5 ft (16.6% of the footprint uncovered, so confidence is "low"). At the data layer
only: a site 2 hip house gives four faces plus two leftovers; a Gardena house with a complex
hip roof fragments into 20 blocks (a known limit); a Huntington Beach address fails cleanly
with "LiDAR too sparse" (Orange County has only 2011/2018 data at 4.5 pts/m²).

## How to run it

```
cd services/roof_measure && make setup && make test            # 99 tests, offline
make measure ADDR="100 Example Ave, Sampletown, CA 90000" # ~7 s cold, JSON + PNG in out/
make serve                                                       # FastAPI on :8011
cd ../../packages/bond_roof && dart test && dart run example/render_fixtures.dart
cd ../../ && make demo-web                                       # or open demos/roof_demo in a simulator
```

The demo works with no service running: the fixture chips load bundled copies of `fixtures/`
(`make sync-fixtures` refreshes them).

## Decisions and open items for John

1. **Roofr's total (5,405 sq ft) is about 1,500 sq ft below the county building outline
   (6,901).** Our 6,760 is not independent evidence: about a quarter of the footprint had no
   LiDAR-fitted block (tree cover, dropped edge cells) and was filled from the outline, so our
   total is largely the outline echoed back. The independent evidence is the 2022 orthophoto,
   which shows the whole outline as roof, and the LiDAR returns on the parts it can see. The
   area our LiDAR actually fitted before gap fill is 5,189 sq ft (`source.lidar.fitted_area_sqft`),
   close to Roofr's 5,405, so the likeliest explanation is that tree canopy hides the same
   roof from Roofr's aerial imagery as from the LiDAR. Ask the owner whether the Roofr report
   was meant to cover the whole building before trusting either number.
2. **Google Solar API** is disabled on Google project <gcp-project-number> (enable at
   https://console.developers.google.com/apis/api/solar.googleapis.com/overview?project=<gcp-project-number>).
   Until then the Solar + agent track runs on a synthetic fixture. Solar's terms ("do not create
   content based on Google Maps Content") are a legal risk for derived diagrams; the LiDAR path
   has no such issue.
3. **Anthropic API credit** is at zero on the key in avalon-crm `.env` (HTTP 400). The Claude
   agent path is coded and unit-tested with a mock but has not run live. `--no-agent` works.
4. **CGAL straight skeleton is GPL** (via `compas_cgal`). It stays server-side; nothing GPL ships
   in the Dart packages or apps.
5. **Coverage** is LA County LiDAR (2023) today. Other counties need their own 3DEP project
   check; the service reports density and refuses below 8 pts/m².

## Known limits of the POC

- Wall flashing, skylights, chimneys, two-story and two-layer areas are not measured.
- Awnings and small low-slope additions under tree canopy are lost (site 1: 2 of 3).
- Complex hip roofs with many intersecting wings fragment (Gardena sample: 20 blocks).
- Parapet is assigned by rule, not measured (0.15 m lips are at the LiDAR noise floor).
- Roof extent includes the overhang beyond the county wall line (up to 0.6 m).
- Labels on very short edges may be hidden on small renders (the renderer reports how many).
- A vertical-unit mismatch in a non-LA LiDAR project, a vacant parcel, or a corrupt cache file
  were found by review and fixed; the service has had one live run outside LA County (Denver),
  which reached the LiDAR step and then failed cleanly for lack of roof returns.

## Next steps when this moves out of POC

- Publish `bond_roof` and `bond_roof_ui` from this repo; apps pin a `git:` dependency to a SHA.
- Deploy `roof_measure` beside the avalon-crm API (Railway) with a persistent cache volume.
- Add a "verify on site" workflow: the office marks each measured quantity confirmed or corrected.
- Enable the Solar API and run the agent track live on ten real buildings before deciding whether
  it adds anything over LiDAR.
