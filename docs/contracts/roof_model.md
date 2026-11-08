# Roof model contract (POC, schema `bond.roof_model/0.1`)

The one document every builder reads. The Python service EMITS this JSON; the Dart
packages CONSUME it. Nothing else crosses the boundary. Changes to this file are made
by the lead only.

## 1. Coordinate frame and units

- All lengths in **feet**, areas in **square feet**, angles in **degrees**.
- Plan coordinates `[x, y]`: x east, y north, feet, origin at the south-west corner of
  the footprint's bounding box. Roof blocks may extend past the footprint (overhang, up to
  0.6 m), so coordinates can be slightly negative; renderers fit to the model's own bounds.
  The service works in the UTM zone of the footprint (EPSG:32611 for Los Angeles) and
  converts by `ft = m / 0.3048` after translating the origin.
- `edges[].points` are plan coordinates; `edges[].length_ft` is the true (slope) length for
  edges on a sloped facet and equals the plan length on flat facets, as report prints it.
- `origin` carries the WGS84 lat/lng of that `[0, 0]` point so a consumer can place the
  model on a map later. `north_deg` is always `0` in this version (plan is true-north up).
- Pitch is `pitch_rise`: the rise in inches over a 12 inch run (`4.0` means 4/12). Flat is
  `pitch_rise <= 0.5` (report prints 0/12). Tilt degrees = `atan(pitch_rise / 12)`.
- Aspect `aspect_deg` is the compass direction the facet faces (0 = N, 90 = E, 180 = S,
  270 = W), the downslope direction. Flat facets have `aspect_deg: null`.
- Slope factor `sf = sqrt(1 + (pitch_rise / 12)^2)`; `area_sqft = plan_area_sqft * sf`.

## 2. JSON shape

```json
{
  "schema": "bond.roof_model/0.1",
  "generated_at": "2026-11-07T21:00:00Z",
  "address": {"line1": "100 Example Ave", "city": "Sampletown", "state": "CA", "zip": "90000",
              "formatted": "100 EXAMPLE AVE, SAMPLETOWN, CA, 90000"},
  "origin": {"lat": 0.0, "lng": 0.0},
  "north_deg": 0,
  "units": "ft",
  "source": {
    "method": "lidar_skeleton",
    "footprint": {"provider": "lacounty_lariac_2020", "id": "SITE1-BLDG", "area_sqft": 6901.0},
    "lidar": {"project": "CA_LosAngeles_1_B23", "acquired": "2023-10-03/2023-12-08",
              "points_on_roof": 12049, "density_per_m2": 19.0},
    "solar": null
  },
  "blocks": [
    {"id": "b1", "form": "hip", "polygon": [[0.0, 32.0], [35.0, 32.0], [35.0, 58.0], [0.0, 58.0]],
     "pitch_rise": 3.9, "ridge_azimuth_deg": 90, "gable_edges": [], "eave_height_ft": 20.5,
     "plan_area_sqft": 910.0}
  ],
  "facets": [
    {"id": "f1", "block": "b1", "kind": "sloped", "polygon": [[0.0, 32.0], [35.0, 32.0], [26.0, 45.0], [9.0, 45.0]],
     "pitch_rise": 3.9, "aspect_deg": 180, "plan_area_sqft": 286.0, "area_sqft": 301.0}
  ],
  "edges": [
    {"id": "e1", "type": "eave", "points": [[0.0, 32.0], [35.0, 32.0]], "length_ft": 35.0,
     "facets": ["f1"]}
  ],
  "holes": [
    {"id": "h1", "kind": "skylight", "polygon": [[10, 40], [13, 40], [13, 43], [10, 43]], "area_sqft": 9.0}
  ],
  "totals": {
    "total_area_sqft": 5405.0, "pitched_area_sqft": 1200.0, "flat_area_sqft": 4205.0,
    "predominant_pitch_rise": 0.0, "predominant_pitch_area_sqft": 4205.0,
    "squares": 54.05,
    "lengths_ft": {"eave": 209.7, "rake": 32.0, "ridge": 7.8, "hip": 76.2, "valley": 0.0,
                   "step_flashing": 50.0, "wall_flashing": 344.4, "parapet": 423.8,
                   "transition": 0.0, "unspecified": 0.0}
  },
  "confidence": {"overall": "medium",
                 "notes": ["Parapet assigned by rule: flat roof edge on the outline.",
                           "Awnings on the south edge detected but under-sized; verify on site."]},
  "warnings": ["Tree canopy overhangs the south edge."],
  "debug": {"png": "site1_debug.png"}
}
```

Rules:

- `blocks[].form` is one of `flat | hip | gable | shed`. `gable_edges` lists indices of the
  block polygon's edges (edge i runs from vertex i to vertex i+1) treated as gable ends.
- `facets[].kind` is `flat | sloped`. Every facet belongs to exactly one block. Facet
  polygons tile the block polygon (holes excluded).
- `edges[].type` is one of `eave | rake | ridge | hip | valley | step_flashing |
  wall_flashing | parapet | transition | unspecified`. Every edge is a straight segment
  (two points). Polylines are split into segments. `facets` lists the 1 or 2 facet ids
  the edge bounds.
- `totals.lengths_ft` has ALL ten keys, zero when absent. `squares = total_area_sqft / 100`.
- `predominant_pitch_rise` is the half-pitch bucket (0, 0.5, 1.0, ...; flat counts as 0) whose
  facets have the largest summed `area_sqft`; ties go to the lower pitch.
- Holes are subtracted from `plan_area_sqft` and `area_sqft` of the facet that contains them
  (report: "Deleted facets (skylights, chimneys) are excluded from the calculations").
- Numbers are unrounded doubles. Rounding is the renderer's job (report prints whole feet
  on the diagram, `ft in` in the legend, whole sq ft for areas).
- `source.method` is `lidar_skeleton | lidar_agent | solar_agent | manual | fixture`.
- `source.lidar.fitted_area_sqft`, when present, is the plan area of blocks fitted to LiDAR
  returns before gap fill; the difference to `total_area_sqft` is footprint area assigned to
  the nearest block without measurement (tree cover, dropped cells).
- `source.solar`, when present: `{"imagery_date": "2023-05-01", "imagery_quality": "HIGH",
  "segments": N}`.

## 3. Edge classification rules (the service implements these; the renderer only draws)

Per block, given its polygon, form and pitch:

- **flat**: every block polygon edge on the footprint outline is `parapet`; an edge shared
  with another block at a higher roof level (step > 1.0 ft) is `wall_flashing` for the lower
  block; an edge shared with another flat block at the same level is `eave` (report draws
  those internal flat-to-flat lines as eaves); an edge shared with a sloped block is the
  sloped block's eave (do not double count).
- **hip / gable** (straight skeleton of the block polygon at uniform pitch): block polygon
  edges are `eave`, except gable edges which are `rake` (and the ridge extends to that
  wall); skeleton edges between faces of two parallel footprint edges are `ridge`; skeleton
  edges from a convex corner are `hip`; from a reflex corner `valley`. Where a sloped
  block's polygon edge meets a higher wall of another block it is `step_flashing` instead
  of eave.
- **shed**: one facet; the high edge is `ridge`, the low edge `eave`, the two sides `rake`.
- Hole outlines are `wall_flashing` when the hole is a chimney or curb (report draws them
  dashed blue); skylight outlines are drawn but carry no edge type (not in totals).
- `transition` is reserved (pitch change within a block); the POC never emits it.

## 4. Diagrams the Dart side produces from the model

1. **Length diagram**: plan view, edges coloured by type (palette below), whole-foot length
   label beside each edge (hidden when the edge is shorter than half the label width, or
   when the label would overlap another label or cross an edge), legend with the
   ten totals as `Xft Yin`, compass rose, footer "Measurements in diagram are rounded for
   display. Some edge lengths may be hidden to avoid overcrowding."
2. **Area diagram**: plan view, facet outlines, label "Flat" + area or "p/12" + area per
   facet, holes dashed, header block with the eight totals (total, pitched, flat, two-story
   area, two-layer area, predominant pitch, predominant pitch area, unspecified pitch area;
   total, pitched, flat, predominant pitch and predominant pitch area are printed as numbers;
   two-story area, two-layer area and unspecified pitch area are not measured in the POC and
   are printed as "n/a").
3. **Summary block**: address, source method and data dates, total area, squares, pitched
   vs flat, predominant pitch, confidence and warnings.

Palette (default, overridable): eave `#2E7D32`, ridge `#8BC34A`, hip `#5E35B1`, valley
`#E53935`, rake `#FBC02D`, step_flashing `#8D6E63` dashed, wall_flashing `#1E88E5` dashed,
parapet `#FB8C00`, transition `#D81B60`, unspecified `#26A69A`. Facet fill: flat
`#E3F2FD`, sloped `#FFF8E1`.

## 5. Fixtures (the contract tests)

`fixtures/site1_truth.json`: the report report for the sample building, hand-digitised
(from the research `ground-truth` agent), in THIS schema with `source.method: "manual"`.
`fixtures/site1_lidar.json`: what the service produced. `fixtures/synthetic_hip.json`,
`fixtures/synthetic_gable.json`, `fixtures/synthetic_flat_parapet.json`: closed-form cases
with known totals. `fixtures/site1_blocks.json` (schema `bond.roof_blocks/0.1`) and
`fixtures/solar_site1_fixture.json` (a synthetic Solar response) are inputs to the service,
not roof models; consumers filter on the `schema` string. Dart `bond_roof` tests load every
roof-model fixture and check: schema parses,
totals recompute from facets and edges within 0.5 sq ft / 0.05 ft, every edge type in the
palette, diagrams render without throwing and hide no more than 30% of labels.
