# roof_measure 0.6.0: the roof model, the totals and the library call

Replaces `contract-0.2.md` (the roof model and totals), `contract-0.3.md` and `contract-0.4.md` for what a consumer reads from a
measurement. Those files stay as the record of the older shapes and of the job API; where they disagree with this file, this
file wins. The envelope contract name is still `bond.roof_model/0.2` and the model schema `bond.roof_model/0.1`;
`pipeline_version` is `0.6.0`. A missing key means "not available", never "checked and fine".

Only the plane engine exists: one facet per measured roof plane, flat (under 2/12) and pitched told apart, typed edges, things
standing on the roof. The inner `model` and the envelope describe ONE roof and carry ONE set of totals.

## The call

```python
measure(address, *, lat=None, lng=None, force=False, deadline_s=180.0, cache_dir, work_dir=None, overpass_urls=None,
        on_stage=None, isolate=True, include_other_buildings=False, building_outline_id=None, points_path=None)
```

Removed in 0.6.0: `engine`, `method`, `hints` (the one hint, `steps`, is retired: a step line between two pitched facets whose
fitted planes agree at the seam is always typed from the planes), `verify`, `anthropic_api_key`, `google_solar_api_key` and
the block-path test hooks. A caller that passes one gets a `TypeError`. `work_dir`, `overpass_urls` and `points_path` (the offline
house-folder hook) stay. Errors, stages, isolation and caching are as in `contract-0.2.md` section 3.

## Totals (`envelope.totals`, and the same values in `model.totals`)

One function (`engine/totals.py`, `roof_totals`) adds up the facets, edges and objects of the drawn roof. THE RULE: `model.totals` is that
function over the model's own rows and `envelope.totals` is exactly its 24 contract keys (never the engine's separate dict, which can differ by
the 0.05 sq ft of a spike the adapter removes). Areas in square feet (sloped), lengths in feet (3D). A test parses this table
and asserts the engine writes exactly these keys, in this order, and no other.

| Key | Meaning |
|---|---|
| `area_sqft` | sloped area of all facets (the pitched and flat parts are rounded to 0.1 first, the area is their sum) |
| `squares` | `area_sqft / 100` |
| `roofing_pitched_sqft` | sloped area of the facets of roof type pitched (2/12 and up) |
| `roofing_flat_sqft` | sloped area of the facets of roof type flat (under 2/12) |
| `planes_pitch_weighted` | area-weighted fitted pitch (rise per 12) of the pitched facets; 0 without any |
| `plane_count` | number of facets |
| `eave_ft` | sum of the `eave` edges |
| `rake_ft` | sum of the `rake` edges |
| `flat_edge_ft` | sum of the `flat_edge` edges (the outer edge of a flat facet) |
| `exposed_edge_ft` | `step_flashing_ft + wall_flashing_ft` plus 2 x (a + b) of every lantern (`size_ft` [a, b]) |
| `eave_rake_ft` | `eave_ft + rake_ft + flat_edge_ft + exposed_edge_ft` |
| `ridge_ft` | sum of the `ridge` edges |
| `hip_ft` | sum of the `hip` edges |
| `valley_ft` | sum of the `valley` edges |
| `ridge_hip_ft` | `ridge_ft + hip_ft` (a lantern's hips are glass and are not added) |
| `step_flashing_ft` | sidewall: a step that runs down the lower slope |
| `wall_flashing_ft` | headwall: a step across the lower slope, or onto a low-slope section |
| `transition_ft` | pitched meets low-slope with no height step |
| `level_change_ft` | a step between two low-slope sections |
| `chimney_count` | objects of kind `chimney` |
| `chimney_perimeter_ft` | sum of 2 x (a + b) of the chimneys |
| `lantern_count` | objects of kind `lantern` |
| `area_sqft_roof_edge` | equal to `area_sqft`; kept for ONE release because phone builds in the field recognise an engine roof by its presence |
| `low_slope_confirm_sqft` | area of the borderline facets (the fitted pitch is within 2 sigma of the 2/12 cut and the facet is over 5% of the roof) |

`unknown` objects are counted nowhere. A count never prices until a person types it.

`model.totals` carries these keys and, beside them, the MODEL-ONLY shape keys that `model.validate` and the Dart readers use:
`lengths_ft` (feet per edge type, the twelve keys of `EDGE_TYPES`, each the sum of the model's edges of that type; `flat_seam`
never appears), `total_area_sqft` (= `area_sqft`), `pitched_area_sqft`, `flat_area_sqft`, `predominant_pitch_rise` and
`predominant_pitch_area_sqft` (the half-step pitch bucket with the most area), and `note`. These are not in the envelope totals.

## model.facets, edges, objects

`model.facets[]`: `id`, `block`, `kind` (`flat` | `sloped`, cut at 0.5/12), `polygon` (feet, model frame), `pitch_rise`,
`aspect_deg` (null for flat), `plan_area_sqft`, `area_sqft`, `roof_type` (`flat` | `pitched`, cut at 2.0/12), `pitch_fit`,
`pitch_sigma`, `borderline`, `supported_pct`, `points`, `rms_ft`, `plane_eq` (`z = a x + b y + c`, x and y in feet, z in feet above ground).

`model.edges[]`: `id`, `type`, `points` (two [x, y] in feet), `length_ft`, `facets` (one or two facet ids). Edge types the engine
can emit, and only these: `eave`, `rake`, `flat_edge`, `ridge`, `hip`, `valley`, `step_flashing`, `wall_flashing`,
`transition`, `level_change`, `flat_seam` (a drawn line between two flat pieces of one deck: in no total, never priced). A step
edge (`level_change`, `step_flashing`, `wall_flashing`) carries `jump_ft` (the measured height step, at least 0.3 m) and `upper`
(the id of the HIGHER facet; it is one of the edge's `facets`). An outline `rake` may carry `high_edge: true` (the level high side
of a shed). `parapet` and `unspecified` stay valid in the schema for older stored results; the engine emits neither.

`model.objects[]`: things standing on the roof, never facets. Each is
`{id, kind, center: [x, y], size_ft: [a, b], polygon: [[x, y], ...], height_ft, facet, returns}`: `id` is `o1`, `o2`, ... in order of
x then y; `kind` is `chimney`, `lantern` or `unknown`; `center` and `polygon` (a closed rectangle, the measured footprint) are in
the model frame, feet; `size_ft` is long side first; `height_ft` is the 95th percentile height above the plane of the facet under
the object; `facet` is the id of that facet; `returns` is the number of LiDAR returns on the object. Never listed: trees, blobs
with more than 30% of their returns outside the outline, blobs beside a tree, blobs on the roof edge (parapets, walls), blobs
thinner than 0.5 m, and planar blobs over 3 m2 (a roof part the facets left out: they set `model.quality.roof_part_missed_sqft`
instead). Skylights are flush with the roof and cannot be seen by LiDAR: they are never listed. A chimney under about 0.6 m
across is not found at 13 returns/m2, and under 1.0 m is not reliably found at 8.

## model.quality

`engine` (`planes/1`), `engine_params` (the parameter hash), `verdict` (`ok` or the first reason), `reasons`, `fit_covered`,
`fit_all`, `fit_clear`, `tree_cover_pct`, `coverage`, `supported_pct`, `density_pts_m2`, `parcel_match`, `outline_source`,
`outline_shift`, `flat_share`, `plane_mismatch_pct`, `outline_covered_pct`, `model_uncovered_pct`, `level_spread_ft`,
`planes_lidar`, `facets_model` and `roof_part_missed_sqft` (square feet of planar blobs over 3 m2 that no facet covers; 0 when
none). Reasons: `lidar_too_sparse`, `low_density`, `outline_mismatch`, `poor_fit`, `planes_not_found`, `not_exact_parcel`,
`low_slope_confirm`, `parcel_street_match`, `other_buildings_on_parcel`, `outline_no_evidence` (a fifth or more of the building
outline has no roof returns, so that part of the roof edge is estimated), `roof_continues` (the roof plane carries on past a
tenth or more of the outline: an attached roof may be missing), `roof_part_missed` (`roof_part_missed_sqft` is a third of a square
or more: check the roof area). `outline_shift` is the distance from the roof returns' centre to the given outline's centre over
the square root of the outline's area; the outline's registration offset and the disagreement left after it are the diagnostics
`edge_shift_m` and `edge_residual_m` (metres). `model.quality.overhang_scale` is gone (the drawn roof is
the one roof).

## Warning codes

The closed list, each with a producer: `footprint_osm`, `footprint_lidar_hull`, `source_unreachable`, `parcel_without_building`,
`other_buildings_on_parcel`, `parcel_street_match`, `low_point_density`, `low_slope_confirm`, `outline_mismatch`, `poor_fit`,
`low_density`, `objects_failed` (the object finder failed: `model.objects` is empty and the chimney and lantern counts are unknown, not zero), `other`. An unknown code becomes `other`. Removed in 0.6.0 (no producer): `footprint_solar`, `method_fallback`,
`verifier_unverified`, `verifier_adjusted`, `verifier_failed`, `verifier_timeout`, `solar_segments_only`,
`agent_failed_fell_back`, `flat_roof_assumed`, `model_failed`, `model_from_planes`.

## Envelope

`contract`, `pipeline_version` (`0.6.0`), `method_used` (`planes`), `footprint_source`, `generated_at`, `model`, `totals`,
`verification` (always `unverified`, `skipped: engine`), `confidence`, `warnings`, `warning_codes`, and the optional
`other_buildings` (with `lot_buildings`, `lot_area_sqft`, `lot_squares` and `lot_outline_perimeter_ft` = `eave_ft + rake_ft +
flat_edge_ft` summed over the buildings, added to `totals` only when `include_other_buildings`) and `nearby_buildings`.
`model.source.method` is `planes`.

## What 0.6.0 removed

Totals keys: `planes_surface_area_sqft`, `area_sqft_wall_line`, `squares_wall_line`, `outline_perimeter_ft`,
`outline_perimeter_wall_ft`, `overhang_ft_median`, `roof_edge_perimeter_geom_ft`, `drip_edge_eave_ft`, `drip_edge_eave_rake_ft`,
`ridge_cap_ridge_ft`, `ridge_cap_ridge_hip_ft`, `predominant_pitch`, `roofing_pitched_squares`, `roofing_flat_squares`,
`area_sqft_measured_edge`, `squares_measured_edge`, `perimeter_measured_edge_ft`, `pitched_area_sqft` and `flat_area_sqft` (as envelope
totals), `facet_count`, `facets`, `lengths_ft` (as an envelope total), `complexity`, `high_edge_ft`. The priced-versus-drawn split
is gone: there is one roof and one area. Old to new: perimeter is `eave_ft + rake_ft + flat_edge_ft`; ridge cap is `ridge_hip_ft`;
drip edge is `eave_ft` or `eave_rake_ft`; area is `area_sqft`; squares is `squares`. Arguments: see "The call". Edge naming: a
step is `step_flashing` or `wall_flashing` (`level_change` only between two low-slope sections); a hint to type the step otherwise
no longer exists. `ridge_hip_ft` is the plain sum: a crease between two low-slope facets is now counted in it.
