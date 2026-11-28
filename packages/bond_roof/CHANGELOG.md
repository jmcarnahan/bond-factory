# Changelog

## Unreleased
- Roof accuracy round (the bullets after this round describe earlier rounds; where they disagree with it, this round holds): the reader follows the 0.6 library contract (`docs/contract-0.6.md`). BREAKING; an app adopts it at its next pin bump.
  - Totals: `RoofEngineTotals` reads exactly the 0.6 keys (area, squares, roofing pitched/flat, low-slope confirm, weighted pitch, plane count,
    eave, rake, flat edge, exposed edge, eave + rake, ridge, hip, valley, ridge + hip, sidewall, headwall, transition, level change,
    chimney count and perimeter, lantern count, `area_sqft_roof_edge`), all nullable. `RoofMeasurement.totals` IS a `RoofEngineTotals`
    (`RoofEnvelopeTotals` is gone). `RoofTotals` keeps its sums and lengths and reads the same keys in `engine`.
  - Removed: `RoofEnvelopeTotals`, `RoofTotalsVariants`, `RoofVerification`, `RoofVerdict`, `RoofComplexity`, `RoofBlock`, `BlockForm`,
    `RoofModel.blocks`, `RoofFacet.block`, `RoofMeasurement.verification`, `RoofTotals.predominantPitchRise` / `predominantPitchAreaSqft`,
    `RoofEngineTotals` fields `planesSurfaceAreaSqft`, `areaSqftWallLine`, `outlinePerimeterFt`, `outlinePerimeterWallFt`,
    `overhangFtMedian`, `roofingPitchedSquares`, `roofingFlatSquares`, `complexity` and the getter `hasRoofing`, `EdgeType.parapet`,
    `EdgeType.legacy`, `EdgeType.isNew04`, `ReportLayout.legendRows`, `DiagramStyle` has no parapet colour. Old keys (`blocks`,
    `verification`, `from_planes`, `planes_only`) stay in `extra` and round-trip.
  - Added: `EdgeType` order is now eave, rake, flat_edge, ridge, hip, valley, step_flashing, wall_flashing, transition, level_change, flat_seam,
    unspecified, with `hasJump` (step, wall and level-change edges carry `jumpFt` and are labelled "12, 8 ft step"); `RoofObject` (with optional `polygon`, drawn when present),
    `ObjectKind`, `RoofModel.objects`; `RoofFigures`, `TotalRow`, `totalRows`; `RoofEngineTotals.knownKeys`, `RoofTotals.ownKeys`;
    `DiagramStyle.objectColors` / `objectFill`; chimney and lantern marks on the length and area diagrams.
  - Legend and totals: only the rows the roof has (no row of zeros, no "n/a" cells); sidewall and headwall flashing, eave + rake,
    exposed edges, ridge + hip (never smaller than ridge), chimney and lantern rows. The area diagram header shows area, pitched and flat
    roofing (when both), pitch, chimney and lantern counts.
  - `pitchLabel`: the whole number (half up) with the fitted value beside it when they differ at the tenth: `4.31` -> `4/12 (4.3)`.
    The footer sentence "Pitch is rounded to the nearest half" is gone.
  - Labels (75 keys; was 93): added `totals_lanterns`, `legend_chimney`, `legend_lantern`, `mark_chimney`, `mark_lantern`, `pitch`, `totals_eave_rake`,
    `totals_exposed_edge`, `totals_ridge_hip`, `totals_sidewall`, `totals_headwall`, `totals_transition`, `totals_chimneys`; removed
    `legend_parapet`, `totals_priced_area`, `totals_as_drawn`, `predominant_pitch`, `predominant_pitch_area`, `two_story_area`,
    `two_layer_area`, `unspecified_pitch_area`, `pitched_area`, `flat_area`, `total_pitched_area`, `total_flat_area`, `squares`,
    `edge_total`, `not_available`, `level_change_jump`, `source_solar`, `solar_segments`, `method_lidar_agent`, `method_solar_agent`,
    `method_manual`, `method_fixture`, `variant_drip_edge_eave`, `variant_drip_edge_eave_rake`, `variant_ridge_cap_ridge`,
    `variant_ridge_cap_ridge_hip`, `verification`, `verdict_pass`, `verdict_adjusted`, `verdict_fail`, `verdict_unverified`. Changed texts:
    `legend_step_flashing` "Sidewall flashing", `legend_wall_flashing` "Headwall flashing", `footer_area`. The source line reads method
    `planes` like `lidar_skeleton`; the Solar line is gone.
  - Objects are decoration: a malformed entry (no kind, no size and no polygon, a polygon under three points, `objects` not a list) is skipped with a parse note; an object with a `polygon` and no `size_ft` takes its size and centre from the polygon; an object whose centre is more than 5 ft off the roof, or on a model with no geometry, is kept but not drawn. A mark is stretched per axis up to 18 px, never uniformly, and a mark with no area is skipped.
  - `pitchLabel` of a non-finite or absurd rise (over 1000) reads "Flat" and never throws. Totals rows now include roof lanterns and unspecified lines, and the legend is built from the same rows as the table. Totals are read key by key: model totals first, the envelope for any key the model lacks. `exposed_edge_ft`, when absent, is sidewall + headwall + lantern perimeters.
  - Old envelopes (block path, 0.2 to 0.5) still open and draw less: see the README, "Older envelopes".
  - `tool/check_envelope.dart` and `unknownEnvelopeKeys` (test/support.dart): every totals key, edge type and object kind an envelope uses is one the reader knows.
- Length diagram legend: a model that carries roof types (an engine model) lists only the edge types that have length, so a flat roof no longer
  shows a column of "0ft 0in" rows; (superseded by the 0.6 round above: every model now lists only the rows it has).
  `ReportLayout.legendRowsFor(n)` now fills column by column for any `n` other than 10.
- `RoofModel.flatAreaSqftByRoofType` / `pitchedAreaSqftByRoofType`: the flat / pitched split as the drawing hatches it (facets
  typed flat) when any facet has a `roof_type`, else the totals' values. The area diagram header and the summary block use
  them, so the header agrees with the hatching. `RoofTotals` keep their 0.5/12 cut (contract).
- Flat seams (roof_measure 0.5.1): `EdgeType.flatSeam` (`flat_seam`), a seam between two flat sections at one level. Drawn
  as a thin dark line (1.2 px, `0xFF5A5A5A`), never labelled, never in the legend, `lengths_ft` or the edge total
  (`RoofTotals.recompute` skips it). Flat-typed facets are outlined in the same stroke on the length diagram (was light grey,
  1 px); other facets draw as before, and every 0.2 and 0.3 envelope draws as before; a 0.4 envelope's flat facets gain the seam-coloured outline. BREAKING only for hosts that `switch` over `EdgeType` without a
  default.
- A `level_change` edge is labelled with its length like every other edge ("24"), plus the step when the jump is 3 ft or
  more ("24, 5 ft step"). The old label that replaced the length with "Step <jump>" is gone; its key `level_change_jump`
  was removed in the 0.6 round. New `RoofLabels` keys `legend_flat_seam` and `level_change_step`.
- Envelope 0.4 (`docs/contract-0.4.md`), additive: old 0.2 and 0.3 envelopes parse, write back and draw exactly as before
  (scene digests of every shipped fixture are identical to the previous commit).
  - BREAKING for hosts that `switch` over `EdgeType` without a default (it has two more values) and for code that assumes
    `RoofTotals.lengthsFt.length == 10`. Additive otherwise. Version is decided at release.
  - `RoofFacet` gains nullable `roofType` (`flat` | `pitched`), `pitchFit`, `pitchSigma`, `borderline`, `supportedPct`,
    `points`, `rmsFt`, `planEq` (`[a, b, c]`) and the getters `isFlatRoofType`, `isBorderline`; written back only when present.
    `RoofFacet` and `RoofEdge` now compare by value (`==`, `hashCode`).
  - `EdgeType` gains `flatEdge` (`flat_edge`) and `levelChange` (`level_change`), placed after the ten old values;
    `EdgeType.legacy` lists the old ten, `isNew04` marks the new two. `RoofEdge.jumpFt` (`jump_ft`). An unknown edge type
    still reads as `unspecified` (noted in `parseNotes`). `RoofTotals.lengthsFt` now always holds all twelve types;
    `toJson` writes the two new ones only when they are not zero.
  - `RoofEngineTotals` (with `RoofComplexity`): the new totals keys (`roofing_pitched_sqft`, `roofing_flat_sqft`,
    `roofing_*_squares`, `low_slope_confirm_sqft`, `area_sqft_wall_line`, `area_sqft_roof_edge`, `outline_perimeter_wall_ft`,
    `overhang_ft_median`, `flat_edge_ft`, `level_change_ft`, `complexity`, and the cost-sheet keys `planes_surface_area_sqft`,
    `planes_pitch_weighted`, `outline_perimeter_ft`), all nullable, on `RoofEnvelopeTotals.engine` and `RoofTotals.engine`.
  - `RoofEngineQuality` (`RoofModel.quality`: engine, fitAll, fitCovered, coverage, supportedPct, densityPtsM2, parcelMatch,
    outlineSource, verdict, raw) and `RoofBuilding` (`RoofModel.building`: parcelId, outlineId, outlineCentroid, chosenBy).
  - Diagrams: a facet typed `flat` is drawn with a neutral fill and a hatch (plain `LinePrim`s, so SVG and PDF need nothing new);
    a borderline facet gets an orange outline and, in the area diagram where it fits, a third label line (`low_slope_marker`);
    the length legend adds "Flat roof edges" and "Level changes" only when the model has them; a level change edge is drawn
    heavier and labelled with its jump. New `DiagramStyle` fields `flatRoofFill`,
    `hatchColor`, `borderlineStroke`, `edgeWidthScale`; new `RoofLabels` keys `legend_flat_edge`, `legend_level_change`,
    `low_slope_marker`, `totals_roofing_pitched`, `totals_roofing_flat`, `totals_low_slope_confirm` (`level_change_jump`, `totals_priced_area`, `totals_as_drawn` were removed in the 0.6 round).
  - `Scene.regions` (`SceneRegion`: facet id and outline in scene pixels) and `Scene.facetAt(point)` let a host find the facet
    under a tap. `ReportLayout.legendRowsFor(count)`.
  - Changed test: `model_test.dart` "pitch buckets" expected `lengthsFt.length == 10`; it now expects `EdgeType.values.length`.
- Tests only: a planes-only envelope (`fixtures/roof_planes_only/`, no facets or edges) parses, and `LengthDiagram`,
  `AreaDiagram` and `SummaryBlock` build on it without throwing. No library change.
- Licence: MIT (LICENSE file added). It was GPL-3.0-or-later with the rest of the repository;
  no code changes.

## 0.2.0 (2026-11-11)
- Added `RoofMeasurement` (0.2 envelope: model, `RoofEnvelopeTotals`, `RoofVerification`, `RoofVerdict`,
  confidence score, warnings, `warningCodes`, `extra`) with `fromJson`, `toJson`, `fromModel` and
  `parseAny` (envelope or bare 0.x model).
- `RoofMeasurement.generatedAt` is nullable (null when absent or unparseable; omitted from `toJson`). `confidence` is clamped to 0..1, contracts other than `bond.roof_model/0.x` are rejected, and an unknown verdict string is kept in `RoofVerification.verdictRaw`.
- Added `RoofTotalsVariants` (drip edge eave / eave + rake, ridge cap ridge / ridge + hip).
- Added `RoofLabels`: every user-visible string with English defaults, `fromMap`, `toMap`, `copyWith`,
  `keys`, `fill`. `fromMap` and `copyWith` accept `Map<String, String?>`; null, empty and whitespace-only values keep the English default. `LengthDiagram`, `AreaDiagram`, `SummaryBlock`, `scenesToPdf`, `feetInches` and
  `pitchLabel` take `labels`. The "n/a" cells are chosen by a null value, not by text.
- Added `ReportLayout { wide, compact }`; the three builders take `layout` and default their size to
  the layout's design size (compact: 400 x 500, two-column legend and figures, text at least 14 px).
  `width` and `height` of the builders are now nullable.
- Tolerant parser: unknown edge type, facet kind, block form and `lengths_ft` key no longer throw; they map
  to `unspecified`, by pitch, `flat` and `RoofTotals.extraLengths`, and are listed in `RoofModel.parseNotes`.
- `RoofModel` split into `model.dart`, `model_parts.dart` and `totals.dart` (public names unchanged).
- Breaking: the contract palette constant on `DiagramStyle` is now `DiagramStyle.report` (renamed).
- `vector_math` constraint `^2.4.0`.

## 0.1.0 (2026-11-07)
- Initial public layout.
- Renamed from its pre-public working name.
- Consumed by git SHA, not by tag.
