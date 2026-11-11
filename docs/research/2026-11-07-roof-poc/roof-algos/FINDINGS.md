# roof-algos findings (2026-11-07). S = this directory.
FACT = I ran it. INFERENCE = read/docs only.

## 1. roofer
- FACT: `pip install roofer` is the WRONG package (v0.0.2, Franck Barbenoire, py2 Deep Zoom tool). Build fails: ModuleNotFoundError: No module named 'PIL' (S/roofer_install.log). No PyPI package for 3DBAG roofer (pip index: only 0.0.2; rooferpy/pyroofer not found).
- FACT: real tool = github.com/3DBAG/roofer (GPL-3.0, active, pushed 2026-11-05; 3DGI repo archived). Prebuilt macOS arm64 binary in releases: v1.0.0 (2026-04-20), v1.1.0-beta.1 (2026-07-30). Ran v1.0.0: S/data/roofer_bin/bin/roofer (tarball lacks +x; chmod +x; static Mach-O arm64, links only system libs). Python bindings (reconstruct(), ReconstructionConfig) exist per docs (INFERENCE, not tried; source build via conan/nix).
- Inputs (FACT from --help-all): LAS/LAZ (building class 6, ground class 2, configurable --bld-class/--grnd-class) + OGR polygon source (GPKG) with CRS (--srs override). Meters CRS. Output: CityJSONSeq (*.city.jsonl) LoD1.2/1.3/2.2 solids with semantics Roof/Wall/Ground and per-building attrs (rf_roof_planes, rf_ridgelines, rf_rmse_lod22, rf_pt_density, rf_nodata_frac...). Per-part azimuth/slope attributes are listed by `-a` but I only derived tilt/azimuth from face normals. NO edge-type labels (no eave/rake/ridge tags), parapets not modelled.
- Command: `roofer --lod12 --lod22 --id-attribute id X.las X.gpkg outdir` ; runs in ~20 ms per synthetic building.
- FACT results (synthetic, sigma 5 cm, ~7 pts/m2; parser S/scripts/roofer_parse.py):
  | scene | roofer faces | area vs truth | pitch |
  | hip 35x26 ft 4/12 | 4 faces, 952 ft2 vs 959 (-0.7%) | 3.6-3.8/12 (biased low, tilt 16.6-17.8 vs 18.4) | az 358/271/91/180 right |
  | flat 60x40 + parapet | 1 face 2400 (exact), parapet ignored (roof at 24.00, rim at 24.61 absent) | flat | |
  | joined | 4 hip faces 885 ft2 vs 959 (-7.7%), tilts 15.0-19.3, flat face 2462 vs 2400 (+2.6%) | 3.2-4.2/12 | |
  Edges derived from mesh: hip scene ridge 10.4 (truth 9), hips+sloped roof/wall edges 84 (truth 75.6), horizontal 119 (122).
- Verdict: usable as an LoD2 faces + pitch/azimuth/area engine, GPL-3.0 (service boundary only; do not link into a closed-source distributed binary without legal check). Edge typing and parapets must be added by us.

## 2. DIY prototype: S/scripts/planes.py (runner S/scripts/run_synth.py, scenes S/scripts/synth.py)
Pipeline: 0.25 m grid + KD-tree labels; locally-sampled sequential RANSAC (3 points from one 1 m neighbourhood, inliers = largest connected blob, refit x4); merge near-coplanar; LS refit + reassignment; label raster -> connected components (drop <3 m2 or <0.9 m wide = parapet rim) -> gap fill -> 3x3 mode filter -> polygons clipped to footprint; tilt, rise/12, compass aspect, area/cos(tilt). Edges: footprint boundary sampled every 5 cm 0.2 m inward -> eave / rake / high_edge / parapet (points >30 cm above plane within 0.6 m) ; interior: height jump >0.3 m => step_flashing (sloped low plane) / wall_flashing (flat); else plane-intersection line, convex => ridge (<5 deg slope) or hip, concave => valley, same aspect different tilt => transition (coded, untested); crease ends snapped to 3-plane junctions.
- FACT: plain Open3D segment_plane sequential RANSAC FAILED on the joined scene (19 planes, spurious 3-5 deg planes); the locally-sampled variant fixed it (kept both: method='o3d' vs 'local').
- Results, sigma 5 cm, 6 pts/m2, mean of 5 seeds (ft / ft2):
  | metric | hip truth/got/err | flat | joined truth/got/err |
  | area | 959.2/958.7/-0.1% | 2400/2395/-0.2% | 3359/3324/-1.0% |
  | planes | 4/4 | 1/1 | 5/5 |
  | pitch | 3.90-3.99 (truth 4.00) | flat | 3.94-4.11 |
  | eave | 122/121.6/-0.3% | | 87/86.6/-0.5% |
  | ridge | 9/8.7/-3% | | 9/9.5/+5% |
  | hip | 75.6/69.7/-7.8% | | 75.6/70.0/-7.4% |
  | parapet | | 200/199.7/-0.2% | 165/163.7/-0.8% |
  | step flashing | | | 35/34.1/-2.5% |
  | false rake | 0.8 | | 0.7 (corner artefacts, sd ~1.5) |
  Hip is biased ~1 ft short per hip (eave-end lost at footprint cut).
- Sensitivity (FACT): density 4/m2 at sigma 5 cm: hip ok, joined eave +8%, parapet -6%, ridge +33%. Sigma 10 cm (treated as 1 sigma, worst case of QL2 RMSEz<=10 cm): area still within 3-5% but edge topology breaks (hips lost, 10 planes in joined, ridge/valley spam). Only sigma ~5 cm hard-surface noise works; need regularisation (snap to footprint-aligned/orthogonal directions, plane merge by adjacency, min-length filters) before real data.

## 3. Pitch accuracy (FACT, S/scripts/pitch_sim.py, data/pitch_sim.txt) LS plane, true 4/12, 100 trials
| facet run x length | pts/m2 | sigma | sd pitch (/12) | 95% |err| |
| 12x20 ft | 4 | 5 cm | 0.06 | 0.12 |
| 12x20 | 4 | 10 cm | 0.11 | 0.23 |
| 12x20 | 8 | 10 cm | 0.08 | 0.17 |
| 12x12 | 4 | 10 cm | 0.16 | 0.30 |
| 8x8 | 4 | 10 cm | 0.41 | 0.79 |
Analytic sd = sigma/(sqrt(N)*run/sqrt(12)) matches. So random noise is fine for a 12 ft facet (rounds to the right integer pitch). The real risks are systematic: a 5-15 cm vertical offset between swaths across one facet shifts pitch +0.24 to +0.73/12; tile roughness; trees; 2016 vintage vs re-roofs.

## 4. Google Solar API (INFERENCE, docs only)
buildingInsights:findClosest -> roofSegmentStats[] with pitchDegrees, azimuthDegrees, stats.areaMeters2/groundAreaMeters2, center, boundingBox, planeHeightAtCenterMeters. Use: for each of our fitted planes, match the segment whose centre falls inside our polygon (or nearest bbox), compare pitch (+-1 deg) and azimuth (+-15 deg) and flag disagreements; or replace our pitch with Solar's when our facet is <8 ft or noisy, keeping our polygons/edges. Coverage/vintage and billing apply; no polygons, so it cannot replace geometry.

## 5. Alternatives (INFERENCE unless noted)
- PDAL: BSD; brew bottle pdal 2.10.2 exists (not installed); PyPI `pdal` has no wheel (needs libpdal). filters.approximatecoplanar/planefit only tag points, no polygons. Worth it only as a LAZ clip/reader; laspy is enough for the POC.
- CGAL shape detection/polygonal surface reconstruction: GPL/LGPL; PyPI cgal-bindings (1.2) has no installable wheel here (FACT: pip download --only-binary fails); brew cgal 6.2.1 exists. Skip.
- PolyFit (Easy3D, GPL-3.0, last push 2025-04) and City3D (GPL-3.0, 2025-09): C++, need CGAL + MIP solver (Gurobi/SCIP), build from source. Skip.
- geoflow: PyPI `geoflow` 0.0.1 is a 3 KB unrelated stub (FACT). geoflow-bundle (C++ CMake, superseded by roofer). Skip.
- 3dfier (GPL-3.0): LoD1 raster extrusion only. Skip.
- ML roof models: Building3D dataset + 2024-26 papers (two-stage wireframe, Points2Model 2025, LOD2-Former 2026 ISPRS Annals) found; I could NOT confirm released weights that run on CPU. Not for the POC.

## Recommended POC pipeline
1. Clip LAZ to footprint buffer (laspy), keep class 6 (and 2 for ground); verify CRS in meters.
2. Run roofer as a subprocess for faces/pitch/azimuth/area (cross-check) and our planes.py for edge typing and parapets; compare plane counts/areas, flag disagreements.
3. Emit JSON roof model (planes polygons, edges by kind, totals). Expected on clean data: area +-2%, pitch +-0.3/12 on facets >=12 ft, eaves/parapets +-3%, ridges +-5%, hips -8% (known bias), step flashing +-3%.
Failure modes: trees overhanging (RANSAC planes broken/holes), noise >=10 cm breaks edge topology, equipment on flat roofs (small planes dropped by 3 m2 filter), small awnings (<3 m2 dropped; below ~8 ft run pitch sd 0.4-0.8/12), footprint misregistration (parapet/eave misclassified), 2016 vintage, eave overhang (footprint at wall line shortens eaves), tile roughness, multi-storey step edges (jump logic assumes one-storey).
Not determined: real-data behaviour (all synthetic), roofer python bindings, v1.1 beta differences, ML weights availability, valley/transition/rake paths untested (no valley or gable in test scenes), two-layer/two-storey area.
Next probes: run both on the real LA County clip once lidar-3dep delivers; add gable+valley+L-shaped synthetic; add regularisation; test roofer --plane-detect-epsilon/--complexity-factor; try roofer 1.1 beta.

# Real data run, site 1 (2023 LiDAR; figures withheld because they identify a real building)

The real-site run used class 1+2 points only, a county outline for the footprint and a height-above-ground filter.
Absolute areas, lengths, extents, coordinates and plane lists are withheld. The conclusions stay.

## roofer on real data (FACT)
- roofer takes class 1 directly (`--bld-class 1`); no pre-classification is needed.
- BAD result: it makes one near-flat face over the whole main roof, merges the hip section into one shallow face plus
  slivers, and creates junk faces from tree canopy at the south and west edges. Only one hip face is recognisable. No edge
  labels. Not usable as-is on a tree-overhung building; it would need tree removal and tuning (`--plane-detect-epsilon`
  0.3 is loose for 3 cm noise).

## planes.py on real data (FACT, thr 8 cm, parapet cue = >10 cm rise within 0.6 m)
Compared with the third-party report (relative only):

| item | ours vs report |
|---|---|
| total area | about 27% high (the outline includes areas the report leaves out) |
| pitched area | about 14% low |
| eaves | about 27% low |
| hips | none found (the two end hip faces were not segmented) |
| ridge | several times too long (the N/S faces run to the block ends) |
| rakes | about 9% low |
| parapet | about 24% low |
| wall flashing | about 74% low |
| step flashing | about 40% high |
| valleys | spurious, none in the report |

Findings: (1) The county outline is about a fifth larger than the report's roof area, so area inside the footprint cannot
match the report; a roof-edge outline or a roof-height clip is needed. (2) The parapet cue works (a 10 cm lip, noise
2-3 cm, about three quarters of the length) but tree clutter adds false hits; the wall-flashing rule "flat roof meeting
a higher flat section" found only a quarter of the printed length because multi-level flat sections merge into one plane
with a drainage tilt. (3) Hip pitch measures 3.9/12 on both faces, against about 3/12 in the lead's estimate; tree points
on the edge may bias the fit. (4) Spurious valleys and ridges come from tilted-flat fragments; flat/flat seams are
filtered, sloped planes under 3 degrees next to flat are not yet.
Cleaning needed before this is usable: tree and clutter removal, flat-plane merging with a drainage-slope tolerance,
a minimum facet size tuned to awnings, hip-face recovery by lowering the minimum point count, and a roof mask in place of
the county outline.

## Real data details (qualitative)
- The three awnings are visible in the raw points as small sloped tile planes (pitch about 3.8-3.9/12) at the right
  positions and counts, each only partly seen under trees. roofer picks up some of them.
- Hip block: the N and S facets have the right pitch and aspect; the ridge and eave positions are right but the ridge
  length, eave versus step-flashing labels on the N and S sides and the hips are wrong, and one valley is spurious.
- Parapets: 0.15 m lips are present but weak; the outline-based cue is noisy (trees and higher walls). Recommendation:
  treat "flat roof + outline edge" as parapet / wall flashing by default and let the user confirm.

## Roof levels (method)
Method: a 0.25 m grid, per-cell value = median of the lowest half of non-ground returns within 0.3 m, cells with a z spread
over 0.5 m dropped (trees, edges, lips).
FINDING 1 (important): the "levels" in a height-above-ground map are TERRAIN, not roof. The ground falls by about 3 m across
the site, so height above ground differs by up to 3 m across the same roof. In absolute z the roof is almost one level, with
steps of only 0.3-0.6 m (ramps, not walls). Wall flashing cannot be derived from height steps in this cloud.
FINDING 2: pure height-continuity grouping fails (one block). Grouping by surface class (flat under 4 degrees from the
gradient of a smoothed raster, or sloped by 45-degree aspect sector) plus continuity under 0.12 m works: about ten blocks
with rms 1-6 cm each. The four hip faces fit at 3.8-4.0/12; three of them match the report's facet areas within about 11%
and one is about a third smaller because its eave-edge cells were dropped.
Implication for the model-driven plan: roof form per block is recoverable (flat versus hip face, pitch, aspect) from this
cloud; wall-flashing and level steps are not. Edges should be constructed from block polygons (skeleton) and wall flashing
assigned by rule or user confirmation.
