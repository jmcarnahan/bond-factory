# Roof measurement POC: research findings (2026-11-07)

Question: can we turn an address into report-style roof diagrams (edge lengths by type, facet
areas, pitch) ourselves, from open data, with a Dart package rendering the result in our apps?

Sample building: site 1 (a real roof; address in local/sites.json, not tracked). The owner's third-party report
(pages 3 and 4, photographed) was the reference; the photographs and the digitisation are no longer tracked.

## Verdicts

| Topic | Verdict | Folder |
|---|---|---|
| LiDAR | YES. USGS 3DEP project CA_LosAngeles_1_B23 (flown Oct-Dec 2023) covers the site 1 and site 2 cities and a third LA County city at 15-21 pts/m², free and keyless (Entwine EPT over HTTPS, pure Python laspy+lazrs). 60 m box: 77k points, 3.4 s, 4.3 MB. Orange County only has 2011/2018 data at 1.6-3.3 pts/m². Classes are 1 and 2 only (no building class). | `lidar-3dep/` |
| Footprint | YES. LA County LARIAC building outlines via ArcGIS REST, keyless, 0.2 s, with height. area and vertex count withheld (real site); the hip block and awnings are merged into one polygon. Microsoft footprints are bulk-only; OSM here is an import of the county outline. | `footprints/` |
| Roof planes from LiDAR | Pitch and area: good (four hip faces at 3.8-4.0/12, three of four hip faces within about 11% of the report's facet areas, the fourth about a third small). Bottom-up edge extraction from plane boundaries: poor (hips 0, spurious valleys). roofer (3DBAG) runs on this Mac but gives no edge labels and merged the hip. Parapets (0.15 m lips) are at the noise floor. | `roof-algos/` |
| Edges | Construct them from a roof MODEL: segment the roof into blocks, decide form and pitch per block, then the straight skeleton (compas_cgal, CGAL) gives ridge/hip/valley exactly (matches closed form to 1e-12). CGAL's skeleton package is GPL: server-side only. | `solar-agent-track/` |
| Google Solar API | Returns per-segment pitch, azimuth and area but no polygons. Disabled on our Google project; the agent track runs on a synthetic fixture until it is enabled. Terms: "do not create content based on Google Maps Content" is a legal risk for derived diagrams; attribution required. | `solar-agent-track/` |
| Dart rendering | Pure-Dart core builds a Scene of primitives; thin drawers for Canvas, PDF (package pdf) and SVG. Web and iOS builds verified. bond-factory is its own pub workspace; apps consume it with a git dependency pinned to a SHA. | `dart-diagrams/` |
| Ground truth | The report's printed totals are internally consistent. Its pitched area equals the hip block plus three awnings. The report's hip pitch is not printed; its hip lengths imply about 4.6-5/12 while LiDAR measures 3.9/12. | withdrawn |

## Unresolved

- The report's total is about a fifth below the county outline area and the LiDAR roof extent. The 2022 NAIP orthophoto
  shows the whole outline as roof. Either the report under-measured, or the report scope excluded part of the building.
  Ask the owner.
- The report's wall-flashing total cannot be located from geometry (most of the located part is the 17 skylight/curb
  openings). The POC assigns parapet and wall flashing by rule and marks them for confirmation.
- Two-storey area, two-layer area and skylights are not measurable from this data.
