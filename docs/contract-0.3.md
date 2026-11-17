# roof_measure envelope 0.3 (additive to 0.2)

`PIPELINE_VERSION` is `0.3.0`; the contract name stays `bond.roof_model/0.2` and every 0.2 key keeps its meaning and its
value. 0.3 only ADDS optional keys and two warning codes (`parcel_street_match`, `agent_failed_fell_back`; and the street-match note moves from `other` to the first). A parser that ignores unknown keys (the Dart `RoofMeasurement`
does) needs no change. `method_used` never gains a new value: a retry or a fallback is a reason code, not a method.
`pipeline_version` keys the result cache, so 0.2.0 results are not reused after the upgrade.
The agent methods behave differently (they no longer raise on an agent failure): see "Agent methods" below and the CHANGELOG.

## What is added

Present whenever the pipeline had LiDAR blocks: `lidar_skeleton`, `lidar_agent` (a successful agent run too; the
metrics then judge the agent's model, and after a fallback the rule model), and `auto` when it stayed on LiDAR.
Absent, never null, for `solar_agent` and for a result with no blocks. **Absent never means "checked and good"**; and
if the check itself failed (logged on the service) `model.quality` is still there with the single reason
`quality_failed` and no numbers, so a consumer can tell a failed check from "no LiDAR".

`planes` and `quality` are internal library modules, not part of the package API; consumers read the envelope.

### `model.planes` (list)

The LiDAR planes, snapped: made disjoint (an overlap goes to the larger plane), gap-free (every uncovered part of the
outline goes to a neighbouring plane), tidied (spikes and zero-width necks removed, vertices closer than 0.5 ft merged
the same way on every plane so shared borders stay shared, no interior angle under 10 degrees) and, unless the parcel
was only a street match, clipped to the footprint. Pieces under 4 sq ft are dropped. Two snapped planes may still overlap by up to 0.5 sq ft and leave micro-gaps under 0.1 sq ft at their borders (the
snapping is clean to about 0.25 ft, not exact); the union equals the footprint within 1%. `[]` when LiDAR ran but no
plane survived (for example every plane lies outside the footprint). One object per plane:

| Key | Type | Meaning |
|---|---|---|
| `id` | string | the LiDAR block id (`k0`, ...) |
| `polygon` | [[x, y], ...] | exterior ring in feet, model frame, counter-clockwise, no repeated last point, 0.01 ft |
| `holes` | [[[x, y], ...], ...] | OPTIONAL, only when another plane lies inside this one: its rings (clockwise) |
| `pitch_rise` | number | rise over 12, 0.01; 0 for a flat plane |
| `aspect_deg` | number or null | compass downslope bearing; null for flat |
| `plan_area_sqft` | number | area of the polygon minus holes, 0.1 |
| `surface_area_sqft` | number | plan area divided by cos(atan(pitch_rise / 12)), 0.1 |
| `height_ft` | number | height above ground, 0.01 |
| `rms_ft` | number | plane-fit residual from LiDAR, 0.001 |
| `filled_pct` | number | share of this plane's final area that came from gap filling, 0.1 |

### `model.quality` (object): metrics only, no label

| Key | Meaning |
|---|---|
| `plane_mismatch_pct` | area-weighted share of the snapped planes whose best-overlap model facet differs by more than 30 degrees of aspect or more than 1.5/12 of pitch. Flat meets flat only: a plane or facet with no aspect, kind `flat` or a pitch under 0.5/12 is flat, and a flat one never meets a sloped one. Null when there are no planes or the check failed. 0.1 |
| `outline_covered_pct` | share of the FOOTPRINT the raw cleaned planes covered before gap filling, measured on the footprint also when the planes are not clipped (street match); 0.0 when no plane touches it; null only when the check failed. 0.1 |
| `model_uncovered_pct` | share of the snapped planes' total plan area that lies OUTSIDE the union of the model's facets (plan view): the extent the model loses, which the mismatch cannot see. 0 when the model covers every plane, 100 when the model has no facet; null with no planes or when the check failed. 0.1 |
| `level_spread_ft` | highest minus lowest plane `height_ft` among the planes that cover at least 5% of the planes' area; a two-level roof shows several feet, a single-level one about 0. Null as above. 0.1 |
| `planes_lidar` | number of snapped planes (= `model.planes` length); when the check failed, the number of LiDAR planes found |
| `facets_model` | number of facets in `model.facets` |
| `reasons` | codes, in this order when present: `multi_plane_simplified` (planes_lidar >= facets_model + 3 and mismatch >= 30), `low_outline_coverage` (covered < 70), `model_misses_roof_area` (`model_uncovered_pct` >= 10), `sparse_lidar` (the `low_point_density` warning), `parcel_street_match`, `other_buildings_on_parcel`, `agent_failed_fell_back` (a `lidar_agent` run fell back to the rules; the retry after a crashed process adds it too), `bad_lidar_block` (a LiDAR block with a NaN or infinite number was left out), `quality_failed` (first and alone but for the copied codes when the check failed) |

Read the metrics together, never `plane_mismatch_pct` alone: a single small LiDAR plane can be snapped over the whole outline and score a mismatch of 0.0. `outline_covered_pct` (and the reason `low_outline_coverage`) says how much of the outline the raw planes really covered, and `model_uncovered_pct` how much of the planes' area the model does not draw.

The consumer decides what is good or rough; the library applies no threshold beyond the reason codes. Point residuals
are not part of the envelope (points are dropped before the model is built).

### `totals` (four more keys, same presence rule; absent when no plane survived or the check failed)

| Key | Meaning |
|---|---|
| `planes_surface_area_sqft` | sum of the planes' surface areas, 0.1 (compare with `area_sqft`) |
| `planes_pitch_weighted` | plan-area-weighted pitch of the planes (rise over 12; flat counts 0), 0.1 |
| `outline_perimeter_ft` | perimeter of the OUTER ring of the union of the planes, 0.1 (courtyard rings and holes are not counted; several separate parts add up) |
| `plane_count` | number of planes |

### Warning codes

`agent_failed_fell_back` (a `lidar_agent`/`solar_agent` run fell back to the rules; see the table in contract-0.2.md 2.3) and `parcel_street_match`, below.

### Warning code `parcel_street_match`

The note "no exact parcel match; used parcel ... (street match)." (also "(nearest match)") now has code
`parcel_street_match` instead of `other`; the sentence is unchanged. It is in the closed list of 2.3. When it is present
the planes are NOT clipped to the footprint (the footprint may belong to a neighbour): they cover the raw planes with
their holes closed; `outline_covered_pct` is still measured against the footprint, so `low_outline_coverage` can fire.

## Evaluating a roof offline

`make -C services/roof_measure eval BLOCKS=<file-or-dir>` runs the rule method on saved block files (no network, no
keys) and prints one row per file: planes, facets, mismatch, coverage, model area, planes surface area, pitch (model /
planes) and reasons. `ARGS="--json out.json --svg dir --envelopes dir"` also writes the metrics, a side-by-side SVG
(model facets left, snapped planes right) and the full envelopes.

## Agent methods (`lidar_agent`, `solar_agent`)

A failure of the agent (API error, truncated or refused reply, no final answer, a geometry error, a timeout of the
agent stage, blocks the model builder rejects) no longer raises: the rule result is returned with the warning code
`agent_failed_fell_back` (see 2.3 of contract-0.2). `method_used` is then `lidar_skeleton` for `lidar_agent`
(`solar_agent` keeps its name: Solar segments have no LiDAR). **A caller that treats "I got an envelope" as "the agent
ran" must check `method_used` or the code.** A `lidar_agent` child killed by a signal is retried once as
`lidar_skeleton`; a `solar_agent` crash still fails the measurement. `solar_agent` plus `agent_failed_fell_back` means the Solar segments were classified by the rules (`method_used` keeps
the name; there is no new method value). A missing, invalid or revoked Anthropic key is NOT
a fallback: it raises (`measurement_failed`, not retryable).
