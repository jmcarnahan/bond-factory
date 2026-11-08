# 3DEP LiDAR for report-style roof reports: findings (lidar-3dep)
All paths under S=(session scratch, not in repo)

## Verdict
YES for this address and region (LA County), for free, no key: a 2023 QL1-class point cloud with about 16-21 pts/m2 is readable
from the public EPT over HTTP using pure Python (laspy+lazrs), 4.3 MB and ~3.4 s for a 60x60 m box. Roof planes, pitch and eave
heights come out cleanly (plane rms 2-3 cm). Caveats: no building classification (class 6 absent), no RGB, and Orange County
only has 2011 (3 pts/m2) or 2018 wildfire-project data (1.6 pts/m2), which is weak for roof edges.

## FACTS
### Geocode
US Census geocoder: site 1 address -> lat/lon (real values in local/test-data/, untracked) (data/geocode.json). Address-range
interpolated, and in the LiDAR it lands on open ground/driveway (ground z ~35-36 m), NOT inside a building. The lead's rough
a longitude guess was ~600 m off. The described building (flat roof + hipped tile, 5,400 sq ft) was not positively identified; the
footprints teammate should supply the true polygon. Nearest roofs: flat-roof building 10-60 m to the NE (z~40.3, ~5 m above ground), residential to the S.

### 1. Projects covering the point (resources.geojson, ept.json; data/*.ept.json)
| project | acquired (GpsTime in clipped points) | density measured in my boxes | classes present | RGB | CRS |
|---|---|---|---|---|---|
| CA_LosAngeles_1_B23 | 2023-10-03 .. 2023-12-08 | 21.4 pts/m2 all returns (18.0 first returns) | 1, 2 only | no | EPT EPSG:3857 (Web Mercator) |
| USGS_LPC_CA_LosAngeles_2016_LAS_2018 | 2016-01-25 | 5.4 pts/m2 | 1, 2 only | no | EPSG:3857 |
| USGS_LPC_CA_WestCoastElNinoUTM11_2016_LAS_2017 | 2016 (bbox covers; 0 points in my box) | none at this spot | n/a | no | EPSG:3857 |
Newest and densest: CA_LosAngeles_1_B23. ept.json: https://usgs-lidar-public.s3.amazonaws.com/CA_LosAngeles_1_B23/ept.json
(216.9 billion points, laszip, schema has ReturnNumber/NumberOfReturns/Classification/ScanAngleRank/GpsTime/ScanChannel, no Red/Green/Blue).
Returns: up to 5 per pulse (counts 1:54628 2:17910 3:4171 4:267 5:24). Z is metres, X/Y in the EPT are Web Mercator metres
(inflated by 1/cos(site latitude)=1.205 horizontally); I reprojected to UTM 11N (EPSG:32611) before any measurement.
Nominal QL (quality level) is NOT in ept.json; the name suggests a QL1 acquisition, which is INFERENCE.

### 2. Download (script scripts/fetch_ept.py; data/sample.npz = copy of data/sample_CA_LosAngeles_1_B23.npz)
Method: read ept.json, root hierarchy ept-hierarchy/0-0-0-0.json, recurse into children whose cube intersects the box
(following -1 counts into sub-hierarchy pages), fetch every non-empty node at EVERY depth (EPT stores points at all depths, not just leaves),
decode with laspy, clip in UTM. 17 nodes, max depth 12, 20 HTTP requests.
- box: 60x60 m (3600 m2) centred on geocode, reprojected to UTM
- points: 77,000 (21.4 pts/m2); class 2 ground 39,342 (10.9/m2); class 1 unclassified 37,658; class 6 building: 0
- z: min 30.61, max 60.56, mean 36.94 m
- GPS time (adjusted standard): 380354199.8 .. 386061064.7 = 2023-10-03 .. 2023-12-08
- density by surface (wide 160 m fetch, data/wide.npz): flat roof NE building 16.7/m2 (16.0 first returns); hipped house roof 21.8/m2; open street class-2 ground 16.6/m2 (20.4 all returns)
- the box holds mostly trees and ground plus a corner of the NE flat roof; no single complete building is inside it

### 3. Visuals
- data/sample_topdown.png (60 m box: scatter coloured by z, plus 0.5 m max-z DSM). Shows flat NE roof at ~40 m (ground ~35), tree crowns (orange/red, ragged), street, S building corners. FACT: flat roof plane and its sharp edges are clearly visible.
- data/wide_dsm.png (160 m context DSM), data/zoom_south.png, data/sloped_patches.png, data/region_w.png, data/region_ne.png (local plane fits: tilt/aspect).
- data/sample_crosssection.png: strip y=22 m through two hipped houses (clean triangular roof profiles, eaves ~2.5 m and ridge ~3.5 m above the street) and strip y=15 m through the NE flat-roof building (flat top at 40.3 m, vertical walls, tree crowns at the left).
- data/hipfit.png: RANSAC planes of one hip roof.
- Hipped section as four sloping planes: YES, seen on the house at about (-60,22) m relative to the geocode (data/region_w.png aspect map shows N/E/S/W quadrants, ~13 deg). This is a neighbouring house, not the described building.
- Parapets: NOT resolved. At the NE flat roof edge the max z is ~0.15 m above the field (40.45 vs 40.30), within noise of a roof edge, so I cannot claim parapet detection. Roof edges themselves (walls) are very sharp.

### 4. Plane fit (scripts/hipfit.py, window 11x11 m around (-60,22), RANSAC thr 8 cm, then SVD refit)
| plane | inliers | tilt | aspect | rms | rise/12 |
|---|---|---|---|---|---|
| 0 | 669 | 13.28 deg | 83 (E) | 3.2 cm | 2.83 |
| 1 | 624 | 14.01 | 264 (W) | 3.2 cm | 2.99 |
| 2 | 328 | 13.85 | 355 (N) | 2.5 cm | 2.96 |
| 3 | 261 | 14.08 | 175 (S) | 2.0 cm | 3.01 |
Mean tilt 13.8 deg -> pitch about 3/12 (2.8-3.0). Ground (class 2 ring median) 37.18 m; eave ~2.5 m and ridge ~3.55 m above ground. Only 78 of 1960 points unassigned.
Across the 160 m area, 82 of 10,806 patches (rms<6 cm) are 20-35 deg and 236 are 12-20 deg, so other roofs have steeper pitches; the method works on them.

### 5. Cost and practicality
- 60 m box: 3.4 s, 4,329,293 bytes, 20 requests. 160 m box: 6.3 s, 8,655,926 bytes, 38 requests (545,276 points). Both from a Mac on home internet.
- Per-address on demand: yes, easily under a minute (INFERENCE for server: S3 is public, no auth; most bytes are wasted since LAZ nodes cover much more than the box, so caching nodes helps).
- Cost: free, anonymous S3 reads (requester-pays not required in my requests). Library: laspy+lazrs wheels, no PDAL.
- Recency: 2023 flight; for 2026 use that is 3 years old, acceptable for roof geometry, not for recent additions or re-roofs. FACT date range 2023-10..12. The 2016 project is too old and sparse.
- Gaps: no building class so footprints from elsewhere are needed; no RGB; trees overhang roofs (see orange blobs) which corrupts planes under canopy; Census geocode may not land on the roof.

### 6. Coverage in the service area (30x30 m probe boxes; 3DEP boundaries from resources.geojson verified with real fetches)
| city | best project | year | all returns/m2 | notes |
|---|---|---|---|---|
| site 1 city | CA_LosAngeles_1_B23 | 2023 | 21.4 (60 m box) | 2016 LA project 5.4/m2 also present |
| site 2 city | CA_LosAngeles_1_B23 | 2023-10-03 | 15.3 (13.1 first) | 2016: 2.9/m2 |
| third LA County city | CA_LosAngeles_1_B23 | 2023-10-15..22 | 15.5 (14.7 first) | 2016: 3.0/m2 |
| Orange County city | USGS_LPC_CA_SoCal_Wildfires_B1_2018 or CA_OrangeCo_2011 | 2018-08-05 / 2011-12-27 | 1.6 / 3.3 | weak; 2023 LA project does not reach it |
| Irvine, OC ([coordinate withheld]) | CA_OrangeCo_2011 only | 2011-12-26 | 3.0 | old and sparse |
Densities in the 30 m probes are lower than the site 1 60 m box partly because of vegetation/pavement mix and per-box edge effects; they are all ground+objects, not roofs only.
Class 6 absent in every probe (classes 1, 2, rarely 18).
Generalisation: LA County (site 1 city, site 2 city, a third city) YES; Orange County NO for roof-edge quality, using 3DEP alone.

## INFERENCE (labelled)
- B23 is QL1 (>=8 pts/m2) given the name and measured 15-21 pts/m2 (measured is fact, QL label is inference).
- Newer Orange County 3DEP acquisitions may exist that are not in my snapshot of resources.geojson (fetched 2026-11-07); I did not check the GitHub commit date.
- The described building is probably nearby, but its exact position is unknown.

## NOT DETERMINED
- True footprint and the described building's measurements (needs a footprint polygon).
- Parapet height detection and the 5,400 sq ft area check.
- Whether OC has newer data at planetarycomputer/other sources.
- Per-flightline scan angle/quality; vertical datum (not read).

## Next probes
1. Take the footprints teammate's polygon (or OSM) for site 1, clip these points, and run the same RANSAC to get the flat and hipped parts.
2. Run a parapet test with a 0.1 m max-z DSM on a building with a known parapet.
3. Look for OC data newer than 2011 (OCSurvey, OC lidar 2018?) and Planetary Computer 3DEP DTM/DSM for fallback.
4. Cache EPT nodes in a bucket to cut 4 MB per call.

## Files
scripts/: fetch_ept.py find.py stats.py plot_top.py plot_wide.py plot_zoom.py patches.py region.py hipsearch.py hipfit.py dens.py city.py
data/: sample.npz (x,y,z UTM11N, cls, inten, rn, nr, gps, ang), sample_topdown.png, sample_crosssection.png, wide.npz, hipfit.png, region_*.png, *.ept.json, geocode.json, resources.geojson
