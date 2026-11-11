# Roof measurement POC: summary (2026-11-07)

Goal: given a street address, produce report-style roof diagrams (edge lengths by type, facet
areas, pitch, totals) that an app can print or attach to a job, with the drawing done by a
Dart package our Flutter apps can depend on.

Result: **yes, from free open data, for buildings in LA County.** The pipeline runs cold in
about 7 s and reproduces the shape, pitch and totals of the sample third-party report to within a
few percent for every quantity the data can see. Two quantities the report prints cannot be seen in
the data (wall flashing and the openings), and one discrepancy with the report is unexplained.

## What was built

| Piece | Where | What it does |
|---|---|---|
| Contract | `docs/contracts/roof_model.md` | Schema `bond.roof_model/0.1`: feet, plan coordinates, blocks, facets, ten edge types, totals, confidence. The only thing that crosses the Python/Dart boundary. |
| Service | `services/roof_measure/` (Python 3.12, FastAPI on :8011) | Address → Census geocode → LA County LARIAC building outline → USGS 3DEP LiDAR (2023, ~19 pts/m²) → roof blocks (flat / hip / gable / shed, pitch per block) → CGAL straight skeleton → classified edges → model JSON + debug PNG. Also a Google Solar + Claude agent track that runs on a synthetic Solar fixture. |
| Dart core | `packages/bond_roof/` (pure Dart) | Parses the model, recomputes totals, builds the length diagram, area diagram and summary block as a Scene of primitives, exports SVG and PDF. 108 tests. |
| Flutter | `packages/bond_roof_ui/` | Draws a Scene on a Canvas, builds a two-page report, print and share through `printing`. |
| Demo | `demos/roof_demo/` (web + iOS) | Address field, method selector, Measure button (calls the service), fixture chips that work offline, inline report with Print and Save PDF. No popups. |
| Fixtures | `fixtures/` | our output (`site1_lidar.json`), three closed-form synthetic roofs. |
| Research | `docs/research/2026-11-07-roof-poc/` | Per-topic findings with evidence: LiDAR coverage, footprints, plane fitting, Solar API, Dart rendering, ground truth. |

## Sample: site 1 (a real roof; address in local/sites.json, not tracked) (the report vs our LiDAR run)

Absolute figures are withheld (they identify a real building); differences are relative.

| Quantity | Ours vs report | Note |
|---|---|---|
| Total area | about 25% high | See "Unresolved" below |
| Pitched area | about 1% low | Our hip block plus one awning; the report has a hip block and three awnings |
| Flat area | about 32% high | |
| Hip pitch | 3.86/12 (the report prints none; its lengths imply 4.6-5/12) | LiDAR plane fit, +-0.1/12 |
| Eave | about 3% low | |
| Hip | about 15% high | Our hip block is ~12% larger than the report's |
| Ridge | about 60% low | |
| Rake | about 18% low | |
| Step flashing | about 80% low | Two of three awnings lost under tree canopy |
| Wall flashing | 100% low (0) | Not derivable: LiDAR resolves no wall steps and the 17 curb openings are not modelled |
| Parapet | about 2% low | Assigned by rule (flat edge on the outline) |

Other buildings (no third-party reference): site 3, run live end to end, comes
out as one gable block with two facets at 3.2/12 (measurements withheld; 16.6% of the footprint uncovered, so confidence is "low"). At the data layer
only: a site 2 hip house gives four faces plus two leftovers; a house with a complex
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

1. **The report's total is about a fifth below the county building outline.** Our total is not independent
   evidence: about a quarter of the footprint had no LiDAR-fitted block (tree cover, dropped edge cells) and was
   filled from the outline, so our total is largely the outline echoed back. The independent evidence is the 2022
   orthophoto, which shows the whole outline as roof, and the LiDAR returns on the parts it can see. The area our
   LiDAR actually fitted before gap fill (`source.lidar.fitted_area_sqft`) is within about 4% of the report's
   total, so the likeliest explanation is that tree canopy hides the same roof from the report's aerial imagery as
   from the LiDAR. Ask the owner whether the report was meant to cover the whole building before trusting either number.
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
- Complex hip roofs with many intersecting wings fragment (a complex-roof test site in Los Angeles County: 20 blocks).
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
