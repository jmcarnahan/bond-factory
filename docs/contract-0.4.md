# roof_measure envelope 0.4 (additive to 0.2 and 0.3): the plane engine and the building choice

Emitted since pipeline `0.5.0` (the plane engine). These are the changes since pipeline `0.4.0`, released as `0.5.0`:
the library preparation (building choice, below) and the engine arrive together; `0.4.1` was only a working label for the
preparation and was never released. The contract name stays
`bond.roof_model/0.2`; every 0.2 and 0.3 key keeps its meaning. 0.4 only ADDS optional keys, two edge types, four warning
codes and the engine's verdict names. A reader that ignores unknown keys needs no change; an old stored result simply lacks
the keys: **a missing key means "not available", never "checked and fine"**.

Status column: **now** = emitted for every county result since `0.5.0`, whatever the engine; **engine** = emitted when the result was measured
with `engine="planes"` (see "Choosing the engine"). Every key in this document is emitted by `0.5.0`.

## Choosing the engine

`measure(..., engine="blocks" | "planes")` (HTTP request field `engine`, same values). `"blocks"` is the default and the
old rectangle-and-skeleton path, unchanged. `"planes"` is the plane engine: one facet per measured roof plane, flat and
pitched told apart at 2/12, the totals and quality below. It needs live LiDAR and `method` `"auto"` or `"lidar_skeleton"`
(no agent, no `blocks_path`, no `solar_fixture`: a `ValueError`); it has no verifier (`verification.verdict` is
`unverified`) and NO fallback to the block path: when it refuses or fails the caller gets the same job codes
(`lidar_too_sparse` under 4 points/m2 on the roof, `no_footprint`, `timeout`, `measurement_failed`) and decides. The result
carries `method_used` `lidar_skeleton` (a validated name; renamed deliberately in a later release) and
`model.quality.engine` `"planes/1"`. `include_other_buildings` measures the other buildings with the same engine. The
service's result cache key includes the engine (and `PIPELINE_VERSION` 0.5.0).

Verification on an engine result: the LLM verifier never runs (not for any `verify` value, not with a key present).
`verification` is the usual shape with `verdict` `"unverified"`, `rounds` 0, zero usage and the extra key
`"skipped": "engine"`, so a reader can tell "not tried" from "tried, not completed". The warning `verifier_unverified` is
NOT emitted for an engine result (nothing was meant to verify it); the engine's own `model.quality.verdict`, `reasons` and
warning codes replace the verifier. `confidence` is still capped as for any unverified result.

## Which building was measured

| Key | Type | Status | Meaning |
|---|---|---|---|
| `model.source.building.parcel_id` | string or null | now | county parcel id (AIN); null when the footprint did not come from the county layer |
| `model.source.building.outline_id` | string | now | the footprint's id: the county outline id (`BLD_ID`, else `OBJECTID`), or the OSM / hull id |
| `model.source.building.outline_centroid` | [lat, lng] | now | a point inside the chosen outline (shapely `representative_point`, not the centroid), WGS84, 7 decimals |
| `model.source.building.chosen_by` | `"auto"` or `"user"` | now | `user` when the caller passed `building_outline_id` |
| `model.quality.parcel_match` | `exact` `street` `nearest` `given` | now | present with `model.quality` and only for a county footprint; see below |

`parcel_match`: `exact` = the parcel's situs house number AND street equal the input text (the text rule is unchanged);
`street` = the number matches, the street does not; `nearest` = neither; `given` = the caller named the outline.
Whatever the label, the PARCEL is the one that contains the caller's point when a point was given (library `lat`/`lng`),
and the outline is the one on that parcel that contains the point or, failing that, the nearest to it. Without a point
(the address was geocoded) the old rule holds: the text match first, the largest outline on the parcel. A weak match
still adds the `parcel_street_match` warning; `given` adds none. `parcel_match` is absent for OSM, Solar and LiDAR-hull
footprints and for a Solar-method result without `model.quality`.

Library call: `measure(..., building_outline_id="<id>")` measures exactly that county outline (the id comes from an
earlier result's `source.building.outline_id`). An id the layer does not know raises `MeasureError` with code
`no_footprint`; a county outage raises `upstream_unavailable`. The chain never substitutes another building for a named one.

## LiDAR project choice (behaviour change, now)

Candidate 3DEP projects whose expected density (project point count over its area) is at least 8.0 points/m2 are
tried first, newest first (roofs change: a 2023 survey at 15 beats a 2016 one at 20); the rest follow, densest first and
newest as the tie-break (an older 13 beats a newer 5); a listing without a point count ranks between the two groups. A
survey that passes the 4.0 test but gives under 8.0 points/m2 on the roof itself does not end the search: the next candidate
is fetched and the denser cloud wins (`meta.roof_density`, `meta.choice`). At most three are tried. Before, the newest always came first.
Unchanged: a project counts only when the roof itself has 4.0 points/m2 or more (`lidar_too_sparse` otherwise), and a thin
or failing first choice falls back to the next.

## The model's frame (engine)

`model.origin` is `{lat, lng}` (as before) plus `epsg`: the projected CRS code of the model's local frame (for example a UTM
zone). The frame's origin is the south-west corner of the footprint's bounding box in that CRS; projecting `origin.lat`,
`origin.lng` with `epsg` gives it (within 1 cm), and a model point is `(metres - origin) / 0.3048` feet. Emitted for
`engine="planes"` results; the block path's `origin` is unchanged (no `epsg`).

## Facets, totals, edges (engine)

`model.facets[]` keep `kind` (`flat` | `sloped`, cut at 0.5/12; a `flat` facet has `pitch_rise` 0 and `aspect_deg` null) and
gain: `roof_type` (`flat` | `pitched`, cut at 2.0/12), `pitch_fit`, `pitch_sigma` (rise per 12; null under 8 points),
`borderline` (true when `pitch_fit` +- 2 sigma straddles 2.0 AND the facet is more than 5% of the roof area),
`supported_pct`, `points`, `rms_ft`, `plane_eq` (`z = a x + b y + c`, x and y in plan feet of the model frame, z in feet
above ground: as in `model.planes`, which for an engine model has one entry per facet). The diagram is drawn at the
MEASURED roof edge (overhang scale 1.0 on county wall-line outlines, 0.25 on other outlines); facets tile that outline.
`model.blocks[]` are one `shed` (or `flat`) block per facet, as for any model built from planes.

Edge types: the closed list of ten (`eave rake ridge hip valley step_flashing wall_flashing parapet transition
unspecified`) gains exactly `flat_edge` (perimeter of a flat facet) and `level_change` (a height jump of 0.3 m or more
between facets, MEASURED FROM THE POINTS on both sides, not from the planes; the edge carries `jump_ft`, runs at the lower
roof's height and has both facets). `model.totals.lengths_ft` always has the ten 0.2 keys and gains `flat_edge` and
`level_change` for an engine model (a model without them reads as zero; any other key is invalid). `step_flashing` and
`wall_flashing` keep their wall meaning and the engine does not emit them.

How the engine types an edge (one typer, `roof_measure/engine/edges.py`; lengths are 3D feet, collinear pieces of one
type between the same facets are one edge):

| Where | Type |
|---|---|
| outline of a flat facet | `flat_edge` |
| outline of a pitched facet, facing down its slope | `eave` |
| outline of a pitched facet, along its slope | `rake` |
| outline of a pitched facet, level, at the top of its slope (a shed or lean-to side) | `rake` with `high_edge: true`; never a `ridge` |
| two facets, jump from points 0.3 m or more | `level_change` (+ `jump_ft`), unless it is a stub (below) |
| two flat facets (under 2/12), no verified jump | no edge: one membrane in two pieces |
| two facets, both fall away from the shared line | `ridge` (level) or `hip` |
| two facets, both rise towards it | `valley` |
| pitched meets a flat facet of real size (8 m2 or more AND 5% of the roof or more) at one height | `transition` |
| pitched meets a smaller flat facet | by the planes (`ridge`, `hip`, `valley`), else no edge |
| a slope that carries on across the line (a kink) | no edge |
| coplanar facets, or two flat facets with no verified jump | no edge (listed in `model.debug.coplanar_seams`: they should have been merged) |

A `level_change` shorter than 1.0 m, or under 0.45 m high and shorter than 2 m, is clutter: it is not drawn as an edge
(the neighbouring chains carry on) and is listed in `model.debug.edge_diagnostics.absorbed_level_changes`. Everything the
typer left out is in `model.debug.edge_diagnostics`: `mergeable`, `kinks`, `small_flat`, `absorbed_level_changes`.

`model.edges[]` entries may carry `jump_ft` (`level_change` only) and `high_edge` (`true`, outline `rake` only).

### Totals and the cost-sheet key map

The engine writes the four existing keys the cost sheet reads, with the PRICED roof-edge numbers (the measured overhang
times `overhang_scale` 0.5 on a county wall-line outline, the facets clipped to that edge):

| Cost sheet line | Key | 0.4 meaning |
|---|---|---|
| Squares | `totals.planes_surface_area_sqft` (then `area_sqft`) | roof-edge surface area |
| Pitch | `totals.planes_pitch_weighted` | area-weighted pitch of the pitched facets (2/12 and up) |
| Drip edge | `totals.outline_perimeter_ft` | roof-edge perimeter (before: the wall line) |
| Ridge cap | `totals.ridge_cap_ridge_hip_ft` | ridge + hip |

New totals: `roofing_pitched_sqft`, `roofing_flat_sqft` (priced surface area split at 2.0/12), `roofing_pitched_squares`,
`roofing_flat_squares`, `low_slope_confirm_sqft` (the borderline facets), `area_sqft_wall_line` (the facets cut to the
wall-line outline), `area_sqft_roof_edge` (the DRAWN area, at the measured roof edge: the facets of `model.facets`),
`outline_perimeter_wall_ft`, `overhang_ft_median`, `flat_edge_ft`, `level_change_ft`, `plane_count` and `complexity`
`{facets, hip_valley_ft_per_square, hint}` with `hint` `"simple"` | `"cut_up"` (14 or more facets, or 7 ft or more of hip and
valley per square). The priced area lies between the wall-line area and the drawn area. `outline_perimeter_ft` is the priced
eave + rake + flat edge, `ridge_cap_ridge_hip_ft` the priced ridge + hip. ONE area for the envelope: `area_sqft`, `squares` (x 100),
`planes_surface_area_sqft` and `roofing_pitched_sqft` + `roofing_flat_sqft` are the same PRICED number (the parts are rounded
to 0.1 first and the area is their sum), and `area_sqft_wall_line` <= it <= `area_sqft_roof_edge`. The inner `model` is the
DRAWN roof: `model.totals` (`total_area_sqft`, `squares`, `lengths_ft`, ...) describe its facets at the measured roof edge
and carry a `note` saying so; the envelope's totals are priced. The existing `pitched_area_sqft` and `flat_area_sqft` keep
their 0.5/12 cut and their meaning. Keys whose value is unknown are left out.

### `model.quality` additions (engine)

`engine` (`"planes/1"`), `engine_params` (the hash of every engine tunable, also part of the service's result cache key),
`fit_covered`, `fit_all`, `fit_clear`, `tree_cover_pct`, `coverage`, `supported_pct`, `density_pts_m2`, `outline_source`,
`overhang_scale`, `outline_shift`, `verdict`, and `reasons`. `fit_all` / `fit_covered` are the share of roof points within
0.15 m of their facet's plane (of all points / of the points inside a facet); `coverage` the share of roof points inside a
facet; `supported_pct` the area-weighted share of each facet that has points under it. The 0.3 keys stay, with engine
analogues: `plane_mismatch_pct` = 100 x (1 - `fit_covered`), `outline_covered_pct` = roof-point support over the outline,
`model_uncovered_pct` = share of points outside every facet, `level_spread_ft`, `planes_lidar` (distinct planes used) and
`facets_model`. `tree_cover_pct` is the share of roof returns more than 0.5 m ABOVE the surface under them (canopy over the eaves) and
`fit_clear` is `fit_all` with that canopy left out of the count. Both are REPORTED only: the verdict does not use them
(a wrong drawn surface, such as a flat drawn over a slope, puts the real roof "above" it, so a canopy-free fit would hide
exactly the roofs `poor_fit` must catch). `poor_fit` tests `fit_all` (below 0.55, over ALL the engine's quality points) and
the supported share (below 70%). `reasons` lists every verdict condition that holds (first = `verdict`), plus `low_slope_confirm` when facets
are borderline and the parcel reasons (`parcel_street_match`, `other_buildings_on_parcel`, `not_exact_parcel`).
`quality_label` in adopting apps keeps its three wire values `good | rough | unchecked`.

| Verdict | Definition |
|---|---|
| `low_density` | 4 <= points on the roof per m2 < 6 (dense is 8 or more; under 4 is refused) |
| `outline_mismatch` | roof-point support covers under 70% or over 130% of the reference outline |
| `poor_fit` | `fit_all` below 0.55 (over all the engine's quality points; canopy is NOT left out), or planar support under 70% |
| `unknown` | the quality signals could not be computed, or the priced roof edge fell back to the drawn one (`priced_fallback`): never `ok` |
| `priced_fallback` (reason, not a verdict) | the priced roof edge could not be built, so the priced totals are the drawn ones; such a result is never `ok` (verdict `unknown`) |
| `planes_not_found` (reason) | (almost) no plane explains the roof points: verdict `poor_fit` |
| `not_exact_parcel` | `parcel_match` is `street` or `nearest` and the user did not choose the building |

### Warning codes (engine)

The closed list gains `low_slope_confirm`, `outline_mismatch`, `poor_fit`, `low_density`: emitted with a plain sentence when
the verdict reasons hold (`low_density`, `outline_mismatch`, `poor_fit`) and when `low_slope_confirm_sqft` is above zero.
`model.source.method` stays one of the validated methods (`lidar_skeleton` until the old path is retired); an engine model
also has `model.source.engine` (`"planes/1"`), `model.source.engine_params` (a hash of every engine tunable), and
`model.source.from_planes` true. `model.debug` carries `coplanar_seams` and `area_check`.

## Roof modelling without CGAL (library internals, now)

`model` and `planes_model` import without `compas_cgal`; only the hip and gable forms of the old rectangle-and-skeleton
path load it, on first use (`roof_measure/ringgeom.py` holds everything CGAL-free; `skeleton.py` re-exports it).
`roof_measure.engine.points.roof_points` is the one place that chooses a building's roof returns, shared by the block
segmenter and the engine. None of this changes a number in a result.
