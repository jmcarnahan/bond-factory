# Solar API + footprint + Claude agent: design (not run)

Status: design only. The Anthropic API and the Solar API were not called. The Solar
input used in the worked example is the SYNTHETIC fixture `data/solar_fixture_site1.json`.
The output schema below is my proposal. I have not seen the Dart-side schema, so align it.

## 1. What the agent is for, and what it is not for

The agent is a decision layer. It picks the roof form of each block and which footprint
edges are gables, from evidence. Every number comes from a tool call. The agent never
writes a length, area or angle itself.

LLM can do: read the Solar table, count distinct azimuths, see that a sloped cluster is
smaller than the footprint, propose where to cut, choose gable edges by comparing facet
azimuths with edge bearings, notice contradictions (area mismatch) and retry a cut.

LLM cannot do (and must not be asked to): estimate lengths, compute skeletons, measure
areas, locate a ridge, know a roof form that Solar data does not reveal (see section 6).

## 2. Inputs

1. `footprint`: list of (x, y) vertices in local feet (EPSG:2229 ftUS shifted so min x, min y = 0),
   edge i = vertex i to vertex i+1. Also the `measure()` output (per-edge length and outward bearing).
2. `solar_segments`: table, one row per `roofSegmentStats`, already placed in the footprint frame by
   `segment_to_footprint_match`: segment id, pitch_degrees, azimuth_degrees, area_sqft (tilt-adjusted),
   ground_area_sqft, bbox_ft (minx, miny, maxx, maxy), center_ft, planeHeightAtCenter (m),
   inside_footprint, dist_to_footprint_ft, form_hint (flat if pitch < 2 deg).
3. `imagery`: imageryDate, imageryQuality (a stale date, e.g. before a re-roof, is a warning).
4. `whole_roof`: wholeRoofStats area (used as a sanity total only).

## 3. Tools (all in `scripts/skeleton.py`, tested)

| Tool | Signature | Returns |
|---|---|---|
| `measure` | `measure(polygon)` | area, perimeter, bounds, per-edge index/length/outward bearing, min rotated rectangle sides |
| `split_footprint` | `split_footprint(polygon, line)` | list of `{polygon, area_sqft}`, largest first; `line` is two points, extended infinitely |
| `segment_to_footprint_match` | `(solar_segments, polygon, origin, to_local)` | table in section 2, item 2 |
| `hip_roof_edges` | `(polygon_ft, pitch_rise, gable_edges=None)` | facets (polygon, true area, pitch, aspect), edges typed eave/rake/ridge/hip/valley with true 3D length, totals |

The agent also needs `rect_fit(polygon)` (minimum rotated rectangle) because the LARIAC footprint has
0.4-2 ft jogs (vertices 39-40, 42-45 on site 1) that make a raw skeleton emit spurious hips and valleys
(measured: raw block gives 133 ft of hips and 51 ft of valleys; a fitted rectangle gives 80 ft and 0). Add it as a fifth tool, or
let `hip_roof_edges` take `simplify_tol_ft`.

## 4. Decision per block and the evidence

Step 1. Classify each Solar segment: flat (pitch < 2 deg) or sloped; inside footprint or not
(a sloped segment 0-15 ft outside the footprint is an overhang or awning: treat it as a separate shed, never as part of the main roof).

Step 2. Cluster sloped segments by location (bbox overlap). For each cluster, count distinct azimuths:

| Evidence in cluster | Roof form | Tool call |
|---|---|---|
| 4 azimuths about 90 deg apart, areas pair up (two long, two short) | hip | `hip_roof_edges(block, rise)` |
| 2 azimuths 180 deg apart | gable; gable edges are the two block edges whose outward bearing is perpendicular to the facet azimuths | `hip_roof_edges(block, rise, gable_edges={i, j})` |
| 1 azimuth | shed: one facet, high edge is a ridge-like top, rakes on the side edges | not covered by the skeleton; use `measure` on the block and report eaves/rakes by bearing, flag as lower confidence |
| 3 azimuths or more than 4 | complex (L, T, cross-gable); split into blocks, each handled as above | `split_footprint` first |
| pitch < 2 deg | flat | `measure(block)`; every outer footprint edge is a parapet or eave per the product rule |

Step 3. Locate the block. The bounding boxes of the sloped segments give the extent. The agent proposes cut
lines along footprint edges (the block's south wall) and perpendicular to the ridge axis (the free end),
calls `split_footprint`, then verifies: block plan area must match the sum of Solar `groundAreaMeters2` for the cluster
within about 5 percent. If not, move the cut and retry (the deterministic pipeline does this with a scan, see `scripts/run_pipeline.py`).

Step 4. Pitch: area-weighted mean of the cluster's pitch_degrees, converted to rise = 12 tan(pitch). Snap to the nearest
half-step only if the spread is under 1 deg.

Step 5. Self-check, then emit JSON: sum of facet areas versus Solar cluster area (flag over 8 percent); number of facets
versus segments; footprint covered versus not covered by any segment.

## 5. Output JSON (proposed roof model)

```json
{
  "units": {"length": "ft", "area": "sqft"},
  "frame": {"epsg": 2229, "origin_ftUS": [x0, y0]},
  "blocks": [{"id": "b1", "form": "hip|gable|shed|flat", "gable_edge_indices": [], "pitch_rise_per_12": 4.61,
              "confidence": "high|medium|low", "evidence": ["4 azimuths 86.6/176.6/266.6/356.6", "..."]}],
  "facets": [{"id": "f1", "block": "b1", "type": "pitched|flat",
              "polygon": [[x, y, z]], "pitch_rise_per_12": 4.61, "aspect_deg": 356.6, "area_sqft": 300.1}],
  "edges": [{"id": "e1", "type": "eave|rake|ridge|hip|valley|parapet|wall_flashing|step_flashing",
             "polyline": [[x, y, z], [x, y, z]], "length_ft": 19.1}],
  "totals": {"roof_area_sqft": 0, "pitched_sqft": 0, "flat_sqft": 0, "eaves_ft": 0, "rakes_ft": 0,
             "ridges_ft": 0, "hips_ft": 0, "valleys_ft": 0, "parapet_ft": 0},
  "warnings": ["..."],
  "provenance": {"footprint": "LARIAC 2020 BLD_ID ...", "solar_imagery_date": "2023-06-15", "attribution": "Includes solar data from Google"}
}
```

Every `length_ft` and `area_sqft` must be copied from a tool result. The harness should
validate that (reject any number not present in a tool output), because the model could otherwise
round or invent.

## 6. Honest limits

1. Solar gives no edges. Whether a flat-looking low-pitch roof has a parapet, and how tall, is invisible to it.
2. Solar pitch/azimuth is a fit per segment. On small hips it can merge or drop facets (the report triangles are 169 and 190 sqft, a Solar segmenter may return one or none).
3. The skeleton assumes uniform pitch and that every non-gable footprint edge is an eave at the same height. Real roofs
   with mixed pitch, dormers, clipped hips, or overhangs break this. Jogs under about 2 ft in the footprint must be regularised first.
4. The footprint is a wall outline (LARIAC 2008-era geometry on this record), not the roof drip line, so eaves and
   hip lengths inherit the width error. On site 1 the fitted block is 27.4 ft wide against about 26 ft implied by the report numbers; that alone moves hips by 5 percent and the ridge by 2 ft.
5. Gable versus hip is decided from azimuth count; a gable with a small hipped (jerkinhead) end has 4 azimuths and would be called a hip.
6. Flat areas: the Solar table covers whatever Google segmented; the footprint covers the whole outline. The two disagree on site 1 (see FINDINGS), and the agent can only flag it.
7. Terms: see FINDINGS section 6. The Solar API permitted use is energy systems. This is the dominant risk of the track, not the geometry.

## 7. System prompt

```
You are a roof-geometry analyst. You receive a building footprint (vertices in feet), a table of Google Solar API
roof segments placed on that footprint, and a set of tools. Your job is to decide, for each part of the roof,
its form (flat, hip, gable, shed) and, for gables, which footprint edges are the gable ends. Then you call the
tools to get every number.

Hard rules:
1. Never estimate, round, convert or compute a length, area, angle or pitch yourself. Every number in your output
   must be copied exactly from a tool result. If you need a number, call a tool.
2. Decide form from evidence, and write the evidence in the output: count the distinct azimuths among sloped segments
   (pitch >= 2 deg) in each spatial cluster. About 4 azimuths 90 deg apart = hip. 2 azimuths 180 deg apart = gable.
   1 azimuth = shed. Pitch < 2 deg = flat. Segments centred outside the footprint are overhangs or awnings:
   handle them as separate shed blocks.
3. Gable edges are the footprint edges of the block whose outward bearing is perpendicular to the facet azimuths.
4. Locate a block with split_footprint, then verify with measure that the block's plan area is within 5 percent of
   the sum of the cluster's ground areas. If not, move the cut and try again, at most 3 times.
5. If the footprint has jogs shorter than 2 ft inside a block, call rect_fit on the block before hip_roof_edges.
6. If evidence is ambiguous or contradictory (area mismatch over 8 percent, 3 or more than 4 azimuths, imagery older
   than the footprint), keep the best guess, set confidence to low, and add a warning that says exactly what is uncertain.
7. Do not invent features (dormers, chimneys, parapet heights) that the data does not show.
8. Output only the JSON in the schema given. No prose.
```

## 8. Worked example: site 1 (synthetic Solar input)

Input: footprint 46 vertices (6,901 sq ft); fixture with 11 segments: 4 sloped at 21.0 deg (areas 190, 289, 169, 300 sqft, azimuths 266.6, 176.6, 86.6, 356.6),
3 sloped at 20.0 deg, azimuth 183, centred 4.0 ft outside the south edge (82, 87, 86 sqft), 4 flat segments (pitch 1.0-1.6 deg, total 4,205 sqft).
The fixture's total is 5,408 sqft against report's 5,405. All of these values are derived from report's report, and the awning positions are invented.

Reasoning the agent should produce:
1. Four segments inside the footprint, pitch 21 deg, azimuths spaced exactly 90 deg apart, two long (300, 289) and two short (169, 190): a hip block. Mean pitch 21.0 deg, rise 4.61/12.
2. Three sloped segments outside the footprint, all azimuth 183: shed awnings on the south wall. Flag as separate blocks.
3. Four flat segments: flat. Every outer footprint edge outside the hip block is a parapet.
4. Block location: sloped-segment bboxes span x -0.2..35.3, y 28.8..58.1. The south wall is footprint edge 37 (the south-facing edge at y about 29-30). Cut along it, then cut perpendicular to the ridge axis.
   `split_footprint` result must give a block plan area close to the 885 sqft of Solar ground area. The scan lands on 33.8 ft along the axis, 885.4 sqft.
5. Call `rect_fit`, then `hip_roof_edges(rect, 4.61)`. Call `measure` on the rest for the parapet.

Tool results (actually run, `scripts/run_pipeline.py`): fitted block 27.4 x 33.2 ft; eaves 121.2, hips 80.3, ridge 5.8, valleys 0, pitched area 974.0 sqft;
flat remainder 6,016 sqft; parapet (outer wall of the rest) 471.9 ft. Comparison with the report truth is in FINDINGS.md section 4.

Expected JSON (abbreviated):

```json
{"blocks": [
  {"id": "b1", "form": "hip", "pitch_rise_per_12": 4.61, "confidence": "high",
   "evidence": ["4 sloped segments inside footprint", "azimuths 86.6/176.6/266.6/356.6 (90 deg spacing)", "plan area 885.4 vs Solar ground area 885.1"]},
  {"id": "b2", "form": "flat", "confidence": "medium", "evidence": ["4 segments pitch 1.0-1.6 deg"]},
  {"id": "b3-b5", "form": "shed", "confidence": "low", "evidence": ["3 sloped segments centred 4.0 ft outside footprint, azimuth 183"]}],
 "totals": {"eaves_ft": 121.2, "hips_ft": 80.3, "ridges_ft": 5.8, "valleys_ft": 0, "pitched_sqft": 974.0, "flat_sqft": 6016.0, "parapet_ft": 471.9},
 "warnings": ["Footprint flat area 6016 sqft exceeds Solar flat total 4205 sqft by 1811 sqft", "Awning edges not computed (outside footprint, shed form unsupported by skeleton)"]}
```

## 9. Cost and risk summary

One agent run is about 6 to 10 tool calls and a few thousand tokens in and out; the deterministic tools are milliseconds. The LLM is needed only when the
roof is not a simple single-form block. For a plain hip or gable, the rule table in section 4 can run without an LLM; the model adds value on composite roofs and in explaining low-confidence output.
