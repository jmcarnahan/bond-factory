# Roof measurement POC: research findings (2026-11-07)

Question: can we turn an address into Roofr-style roof diagrams (edge lengths by type, facet
areas, pitch) ourselves, from open data, with a Dart package rendering the result in our apps?

Sample building: site 1 (a real roof; address in local/sites.json, not tracked). The owner's Roofr report
(pages 3 and 4, photographed, in `ground-truth/`) is the ground truth.

## Verdicts

| Topic | Verdict | Folder |
|---|---|---|
| LiDAR | YES. USGS 3DEP project CA_LosAngeles_1_B23 (flown Oct-Dec 2023) covers the site 1 and site 2 cities and a third LA County city at 15-21 pts/m², free and keyless (Entwine EPT over HTTPS, pure Python laspy+lazrs). 60 m box: 77k points, 3.4 s, 4.3 MB. Orange County only has 2011/2018 data at 1.6-3.3 pts/m². Classes are 1 and 2 only (no building class). | `lidar-3dep/` |
| Footprint | YES. LA County LARIAC building outlines via ArcGIS REST, keyless, 0.2 s, with height. 6,901 sq ft, 46 vertices for the sample; the hip block and awnings are merged into one polygon. Microsoft footprints are bulk-only; OSM here is an import of the county outline. | `footprints/` |
| Roof planes from LiDAR | Pitch and area: good (four hip faces at 3.8-4.0/12, true areas 298/172/124/256 vs Roofr 300/169/190/289). Bottom-up edge extraction from plane boundaries: poor (hips 0, spurious valleys). roofer (3DBAG) runs on this Mac but gives no edge labels and merged the hip. Parapets (0.15 m lips) are at the noise floor. | `roof-algos/` |
| Edges | Construct them from a roof MODEL: segment the roof into blocks, decide form and pitch per block, then the straight skeleton (compas_cgal, CGAL) gives ridge/hip/valley exactly (matches closed form to 1e-12). CGAL's skeleton package is GPL: server-side only. | `solar-agent-track/` |
| Google Solar API | Returns per-segment pitch, azimuth and area but no polygons. Disabled on our Google project; the agent track runs on a synthetic fixture until it is enabled. Terms: "do not create content based on Google Maps Content" is a legal risk for derived diagrams; attribution required. | `solar-agent-track/` |
| Dart rendering | Pure-Dart core builds a Scene of primitives; thin drawers for Canvas, PDF (package pdf) and SVG. Web and iOS builds verified. bond-factory is its own pub workspace; apps consume it with a git dependency pinned to a SHA. | `dart-diagrams/` |
| Ground truth | Roofr's printed totals are internally consistent. Pitched 1,200 = hip 948 + three awnings 255. Roofr's hip pitch is not printed; its hip lengths imply about 4.6-5/12 while LiDAR measures 3.9/12. | `ground-truth/` |

## Unresolved

- Roofr's total (5,405 sq ft) is about 1,500 sq ft less than the county outline (6,901) and the
  LiDAR roof extent. The 2022 NAIP orthophoto shows the whole outline as roof. Either Roofr
  under-measured, or the report scope excluded part of the building. Ask the owner.
- Roofr's "wall flashing 344 ft" cannot be located from geometry (about 232 ft of it is the 17
  skylight/curb openings). The POC assigns parapet and wall flashing by rule and marks them for
  confirmation.
- Two-storey area, two-layer area and skylights are not measurable from this data.
