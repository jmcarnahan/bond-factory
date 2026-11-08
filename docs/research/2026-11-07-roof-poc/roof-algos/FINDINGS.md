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

# REAL DATA RUN (2023 LiDAR, target building, LARIAC footprint 6,898 ft2)
Inputs: wide.npz (already UTM 11N, class 1+2 only), footprint reprojected 4326->32611. Roof candidates = class!=2, inside footprint+0.3 m, HAG>1.5 m (HAG from median of 8 nearest class-2 pts): 12,049 pts, 18.8 pts/m2. Scripts: scripts/real_prep.py, real_run.py, real_plot.py, real_roofer.py, real_roofer_plot.py. PNGs: data/real_planes_result.png (planes.py: facets + typed edges), data/real_roofer.png (roofer faces), Figure: real_overview.png (local only, not tracked: local/research-images/real_overview.png; it shows real coordinates).
## roofer on real data (FACT)
- roofer takes class 1 directly: `roofer --lod12 --lod22 --id-attribute id --bld-class 1 raw.las fp.gpkg out` works on the delivered file (no pre-classification needed; it also worked with my pre-classified class-6 file). h_ground 30.59, pt_density 18.2.
- BAD result: rf_roof_planes 36 (raw) / 33 (pre), rmse_lod22 1.12 / 0.88 m, total roof faces 6,800 ft2. It makes one 5,156 ft2 near-flat face (0.3/12) over the whole main roof, merges the hip section into a 411 ft2 1.3/12 face plus slivers, and creates junk faces from tree canopy at the south/west edges (pitches 3-9/12 at z 34-46 m). Hip N face 171-211 ft2 at 2.7-4.1/12 is the only recognisable hip piece. No edge labels. Not usable as-is on a tree-overhung building; would need tree removal (e.g. only first/last-return logic, HAG cap, or manual mask) and tuning (--plane-detect-epsilon 0.3 default is loose for 3 cm noise).
## planes.py on real data (FACT, thr 8 cm, parapet cue = >10 cm rise within 0.6 m)
| item | truth (report) | ours |
| total area ft2 | 5,405 | 6,889 (+27%) |
| flat / pitched ft2 | 4,205 / 1,200 | 5,857 / 1,032 |
| eaves ft | 209.7 | 153 |
| hips | 76.2 | 0 (E/W hip faces not found) |
| ridge | 7.75 | 42 (ridge runs the full 10 m: N/S faces extend to the ends; plus spurious) |
| rakes | 32.0 | 29 |
| parapet | 423.8 | 324 |
| wall flashing | 344.4 | 90 |
| step flashing | 50.0 | 70 |
| valley (spurious) | 0 | 56 |
| facets | 4 hip + 3 awnings + flat | 14 planes: hip N 3.9/12 (17.9 deg, 514 ft2), S 3.9/12 (391 ft2), flat plane splits (tilt 0.5-1.2 deg), 2 spurious 2.8 deg |
Findings: (1) The LARIAC outline is 6,898 ft2 but the report counts 5,405 ft2 of roof: 1,500 ft2 (22%) of the outline is not in the report roof (patios/overhang/lower roofs/different outline source), so area-inside-footprint cannot match the report; need the outline from a roof-edge source or clip by roof-height class. (2) Parapet cue works: ~10 cm lip gives 324 ft of 424 (76%) with noise 2-3 cm, but tree clutter along S/W edge adds false hits; the wall/parapet split vs "wall flashing" needs the rule 'flat roof meeting higher flat section = wall flashing' which found only 90 of 344 ft because multi-level flat sections are merged into one tilted-drainage plane (flat roofs here have 0.25/12-ish drainage slope, tilt 1.1-1.2 deg, so several 'flat' planes appear; a 1 m step test on 0.3 m threshold is fine, but small steps were lost to plane merging). (3) Hip pitch measured 3.9/12 (N and S faces agree, both 17.9 deg) vs the lead's ~3/12; z profile across the ridge at y=11/13/15 gives rise 0.55 m over ~2 m = ~3.3/12, so plane-fit slope may be biased by tree points on the edge; unverified. Hip ends are only ~1-2 m wide and under trees at the west end. (4) Spurious valleys/ridges come from tilted-flat fragments; filter flat/flat seams (done) and sloped planes <3 deg adjacent to flat (not done).
Cleaning needed before this is usable: tree/clutter removal (above-roof outliers, vegetation by return number or planarity), flat-plane merging with drainage slope tolerance (<2 deg, adjacent, dz<0.3 m), min facet size tuned to awnings (7 m2), E/W hip face recovery by lowering min points, and a reliable roof mask instead of the LARIAC outline.

## Real data: site 1 (requested deliverables; same run as above)
- Files: data/site1.laz (class 6 = footprint+0.5 m, non-ground, HAG>1.5 m; 136,985 pts; 12,486 class 6), data/site1_fp.gpkg (EPSG:32611), data/site1_result.png, scripts/hel_detail.py. NOTE: wide.npz x/y are already UTM 11N metres (372081..372241, 3745456..3745616), not 3857; only the footprint needed reprojecting. Footprint area after reprojection 6,898 ft2 (matches 6,901).
- roofer faces (pre-classified run), by area: 5129 ft2 0.3/12 (main roof), 417 ft2 1.2/12 az 51 (hip block, merged), 230 ft2 0.2/12 z 37.4 (low west strip), 211 ft2 4.1/12 az 355, 130 ft2 2.6/12 az 280, 108 0.9/12, 102 0.5/12, 87 0.8/12 az 265, then 12 smaller faces (many tree junk, tilts 6-9/12 at z 41-46). Full list printed by scripts/hel_detail.py (20 faces). In the RAW run (--bld-class 1) three south faces 73 (3.9/12 az 173), 98 (2.9/12 az 229), 81 (3.5/12 az 175) ft2 appear along the south edge near x 26-36 m: these match the three awnings (82/87/86) within ~15%. In the pre-classified run only two ~49 ft2 4.0/12 az 173-175 faces survive there (the HAG filter or footprint clip shrank them). So awnings ARE visible in the points as sloped tile planes, and roofer can pick them up.
- Hip block edges from planes.py (local metres, block ~ x 4-14, y 9-18): ridge 28.3 ft along y=13 (WRONG length: truth 7.75 ft; direction and position right; the N and S facets are right but run to the block ends because E/W hip faces were not segmented), eaves/step flashing: south long side step_flashing 31.8 ft at y 7.8 is spurious (that is the south hip face meeting the lower flat; the true edge is an eave) and north side step_flashing 34.6 ft at y 17.6 should be an eave (truth eaves 209.8 total) , east side three rakes 3.6+10.9+11.7 ft should be the east hip face edges (hips), valley 21 ft at y 9.1 spurious, wall_flashing 3.9 and 5.5 ft at the west edge plausibly right (W side meets flat/lower). Correct: ridge position/direction, N/S facet pitch (3.9/12) and aspect (0/180), rakes+eaves existence. Wrong: hips (0 found), ridge length, eave vs step flashing on N and S, spurious valley.
- Parapets: 0.15 m lips are present but weak. Along the outline, points within 0.5 m rise above the main flat plane by >0.10 m on 33% of samples (>0.15 m on 27%); but median excess is -0.20 m (outline often sits on the lower side of the roof edge or on a lower roof) and the 90th percentile is +4.75 m (trees and higher walls), so the outline-based cue is noisy. planes.py reported 324 ft parapet vs 424 truth by requiring >0.10 m within 0.6 m of >50% of an edge segment, which also catches tree points. Recommendation: treat 'flat roof + outline edge' as parapet/wall flashing by default and let the user confirm; use the lip detection only to rank confidence.

## Roof levels (scripts/levels.py, data/levels.json, data/levels_out.txt = full output)
Method: 0.25 m grid, per-cell value = median of lowest 50% of non-ground returns within 0.3 m (HAG>1.5 m), cells with z spread >0.5 m dropped (2,946 of 9,975 cells: trees, edges, lips). 
FINDING 1 (important): the 'levels' in the height-above-ground map are TERRAIN, not roof. Class-2 ground median: north half 31.4 m, south half 34.4 m, east third 33.2 m, west third 34.3 m (3 m of fall), so HAG differs by up to 3 m across the same roof. In absolute z the roof is almost one level: flat blocks at z 39.68, 39.98, 40.27/40.34 (steps of only 0.3-0.6 m, ramps not walls) and hip faces 40.2-41.4. So walls between 'levels' are not visible as big steps; wall flashing cannot be derived from height steps in this cloud.
FINDING 2: pure height-continuity grouping fails (1 block, rms 0.27 m; steps are blurred to <0.1 m per cell). Grouping by surface class (flat <4 deg from the gradient of a 5x5 smoothed raster, or sloped by 45-degree aspect sector) + continuity (<0.12 m) works: 10 blocks, rms 0.01-0.06 m each. Histogram of cell z (0.3 m bins) peaks at 39.4, 39.7, 40.0 (3,001 cells), 40.3 and a hip tail to 41.2.
Per block (plan areas; true area = plan/cos tilt):
| # | plan ft2 | mean z | kind | pitch / aspect | rms m |
| 0 | 2016 | 40.27 | flat | 0.19/12 | 0.020 |
| 2 | 574 | 39.98 | flat | 0.27/12 | 0.009 |
| 5 | 183 | 40.34 | flat | 0.05/12 | 0.024 |
| 6 | 847 | 39.68 | flat (NE wing) | 0.24/12 | 0.020 |
| 4 | 284 (true 298) | 40.72 | hip S face | 3.81/12 az 178 | 0.040 |
| 7 | 163 (172) | 40.85 | hip W face | 3.87/12 az 269 | 0.061 |
| 8 | 117 (124) | 40.82 | hip E face | 4.00/12 az 86 | 0.027 |
| 9 | 244 (256) | 40.92 | hip N face | 3.91/12 az 356 | 0.028 |
| 3 | 146 | 39.86 | sloped ramp between flat 2 and 6 | 2.44/12 az 358 | 0.032 |
| 1 | 65 | 39.99 | small south-facing slope at x 17-19 m | 3.69/12 az 180 | 0.038 |
Coverage: blocks 4,350 of 6,898 ft2 inside the outline (rest = trees, spread-dropped cells, parapet strips, areas not roof).
Shared borders (length ft, B minus A step m): hip faces 4-7 16.8 (-0.08), 4-8 16.4 (-0.11), 4-9 10.0 (+0.05), 7-9 18.6 (+0.11), 8-9 17.4 (0.00) [these are the ridge/hip creases: the ridge/hip lines are visible in the map]; 0-4 25.0 (+0.04) hip S eave meeting flat; 0-1 21.4 (-0.07); 0-5 51.4 (+0.01); 2-3 29.3 (-0.07); 3-6 28.7 (-0.04). All steps are <=0.11 m at the borders (smoothed values), i.e. no wall steps are resolved between blocks. Outline length per block is printed in data/levels_out.txt (block 0 48 ft, 4: 17.5, 5: 15.8, 1: 15.5, 2: 12.5, 3: 3.6; remaining outline is on dropped cells).
NW HIP BLOCK (union of the 4 faces): plan 780 ft2, true area 849 ft2; faces true 298/172/124/256 ft2 vs report 300/169/190/289 (S and W within 2%, E 35% low, N 11% low because eave-edge cells were dropped); bounds x 4.0-14.7 m, y 8.8-17.0 m = about 35 x 27 ft ; pitch 3.8-4.0/12 (mean 3.90) with tree and edge cells removed (the 'about 3/12' in the report is not supported; each face fits at rms 3-6 cm); ridge z 41.39, lowest face cells 40.19 (true eave edge is lower, dropped as spread>0.5), cell rise 1.20 m; flat roof beside it is z 40.27 so the hip eave is at the flat-roof level, which is why no wall step shows.
SOUTH EDGE (windows 4 m wide along the south outline; 'inside' = first 1 m inside the outline, 'outside' = 0-3 m south): outside windows are tree scatter (z sd 1.9-5.4 m, best plane only 7-14% of 236-346 points, HAG median 2.7-11 m); no planar awning surface outside. Inside the first metre: x 26-30 has a south-facing plane 23/96 pts at z 39.55 (3.8/12 az 181); x 34-38 has 32/59 pts (54%) at z 39.18 (3.9/12 az 175); x 22-26 outside has 32/236 pts at z 39.53 (3.8/12 az 170); x 14-18 and 22-26 inside are flat roof (51/64 pts planar, sd 9 cm for 22-26). So three small south-facing tile planes at about 3.8-3.9/12 (z 39.2-39.6, about 0.7-1.0 m below the flat roof, not 3 m above ground) are present at x about 22-26, 26-30 and 34-38 m, each only 13-30 ft2 of points per window (trees hide the rest): they match the three awnings in count, pitch and position, but their full 82/87/86 ft2 extents are not recoverable from this cloud without tree removal.
Parapets: see earlier section (0.15 m lips are barely above noise; use default 'flat roof outline = parapet / wall flashing, user confirms').
Implication for the model-driven plan: roof form per block is recoverable (flat vs hip face, pitch 3.9/12, aspect) from this cloud; wall-flashing / level steps are not; edges should be constructed from block polygons (skeleton) and wall flashing assigned by rule/user confirmation.
