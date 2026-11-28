# bond_roof

Pure Dart (no Flutter). Parses the roof model JSON (`bond.roof_model/0.1`, see
`docs/contracts/roof_model.md`) and the service envelope as the 0.6 library writes it, recomputes totals, and lays out three diagrams as
device-independent scenes that can be written to SVG or PDF or painted by a Flutter widget. An envelope of an older shape (the block path of
0.2 and 0.3, the 0.4 and 0.5 engine) still opens and draws less: see "Older envelopes".

`dart test` and `dart analyze` need only the Dart SDK. No codegen: `fromJson` and `toJson` are
hand-written. No network access.

## API

| Import | Name | What it is |
|---|---|---|
| `bond_roof.dart` | `RoofModel.fromJson` / `toJson` | Parse and write the contract JSON. Throws `FormatException` starting with the JSON path (`edges[3].polygon: ...`) for structural errors. An unknown edge type, facet kind, object kind or `lengths_ft` key is mapped (`unspecified`, by pitch, `unknown`, `extraLengths`) and recorded in `RoofModel.parseNotes`. Unknown top-level keys (`origin`, `generated_at`, `debug`, an old `blocks`) survive a round trip in `extra`. |
| | `RoofMeasurement.parseAny(json)` | Reads an envelope (model, `totals` as `RoofEngineTotals`, confidence, warnings and `warning_codes`) or wraps a bare model. Unknown top-level keys (an old `verification`) survive in `extra`. |
| | `RoofEngineTotals` | The 0.6 totals keys, all nullable: area, squares, pitched and flat roofing, weighted pitch, plane count, eave, rake, flat edge, exposed edge, eave + rake, ridge, hip, valley, ridge + hip, sidewall (`stepFlashingFt`), headwall (`wallFlashingFt`), transition, level change, chimney and lantern counts. A missing key is null, never zero. `RoofEngineTotals.knownKeys` lists what it reads. |
| | `RoofObject`, `RoofModel.objects` | What stands on the roof: `chimney`, `lantern` or `unknown`, with centre, size in feet, height, facet and LiDAR returns. Drawn as a small outlined rectangle with a one-letter mark; never a facet, never in an area. |
| | `RoofFigures.of(model)`, `totalRows(model, labels)` | The figures of one roof in ONE place (the 0.6 key when the model has it, else summed from its facets and edges) and the totals rows the summary and the totals table print: only the rows the roof has; ridge + hip is never smaller than ridge. |
| | `RoofLabels` | Every user-visible string with English defaults; `RoofLabels.fromMap(map)` overrides by `RoofLabels.keys`, `{name}` placeholders in templates. |
| | `ReportLayout` | `wide` (1600 x 1000, 3-column legend) or `compact` (400 x 500, 2 columns, text sized for a phone card) for the three builders. |
| | Facet and model extras | Facet `roofType` / `pitchFit` / `pitchSigma` / `borderline` / `supportedPct` / `points` / `rmsFt` / `planEq`; edge types `flatEdge`, `levelChange`, `stepFlashing` (sidewall), `wallFlashing` (headwall) with `RoofEdge.jumpFt`; `RoofModel.quality` and `RoofModel.building`. |
| | `Scene.regions`, `Scene.facetAt(point)` | Facet outlines in scene pixels (not drawn) so a host can map a tap to a facet id. |
| | `RoofModel.recomputeTotals()` | Totals from facets and edges, same rules as the contract. |
| | `RoofModel.bounds` | Bounding box of all geometry, feet. |
| | `feetInches`, `wholeFeet`, `sqft`, `pitchLabel` | Number formats: `209ft 8in`, `35`, `2,121`; the pitch as the whole number (half up) with the fit beside it when they differ at the tenth: `4.31` is `4/12 (4.3)`, `5.0` is `5/12`, a rise of 0.5 or less is `Flat`. |
| | `LengthDiagram.build(model, {labels, layout})` | Edges by type, whole-foot labels (a step edge adds its jump: `12, 8 ft step`), chimney and lantern marks, a legend of only what the roof has (edge rows, eave + rake, ridge + hip, exposed edges, the objects), compass, footer. |
| | `AreaDiagram.build(model, {labels, layout})` | Facet outlines, pitch and area per facet, dashed holes, chimney and lantern marks, the totals the roof has (area, pitched and flat roofing, pitch, chimney and lantern counts). |
| | `SummaryBlock.build(model, {width, labels, layout})` | Text report; height grows with content. |
| | `DiagramStyle` | Palette and sizes (`DiagramStyle.report` is the contract palette). |
| | `Scene`, `LinePrim`, `PolyPrim`, `TextPrim` | The drawing primitives. Logical pixels, y down, ARGB colours, text centred vertically on its anchor point. |
| | `sceneToSvg(scene)` | SVG string. |
| `roof_pdf.dart` | `scenesToPdf(scenes, {fontTtf, title, labels})` | One PDF page per scene, 792 pt wide. Separate import so web apps do not pull in `package:pdf`. |

`Scene.hiddenLabels` counts length labels (or facet labels) left off; `Scene.placedLabels` counts
the ones drawn.

### Hosts: reading the 0.6 envelope

- Draw nothing yourself for flat roofs: a facet with `roofType == 'flat'` is hatched by the scenes, a `borderline` one is outlined
  in orange (area diagram: a third line from the `low_slope_marker` label, when it fits). All text comes from `RoofLabels`; pass your
  translations for every key in `RoofLabels.keys` (the new ones of 0.6: `legend_chimney`, `legend_lantern`, `mark_chimney`,
  `mark_lantern`, `pitch`, `totals_eave_rake`, `totals_exposed_edge`, `totals_ridge_hip`, `totals_sidewall`, `totals_headwall`,
  `totals_transition`, `totals_chimneys`, `totals_lanterns`). The default texts of `legend_step_flashing` and `legend_wall_flashing` are now
  "Sidewall flashing" and "Headwall flashing".
- `lengthsFt` has one entry per `EdgeType` (eleven types and `unspecified`). Code that switches over `EdgeType` must handle all of them;
  `parapet` is gone (an old parapet edge reads as `unspecified`).
- A user's flat / pitched correction is the host's business: tap a facet (see `bond_roof_ui`), show inline controls, send the change
  to the service, and draw the next measurement.
- To check an envelope against the reader: `dart run tool/check_envelope.dart file.json` lists every totals key, edge type and object kind
  the reader does not know (exit code 1); in a test, `expect(unknownEnvelopeKeys(json), isEmpty)` from `test/support.dart`.

### Older envelopes

An envelope or model of an older shape does not throw. It draws its facets and edges, with the totals its own facets and edges give (area,
the pitch weighted over its pitched facets, a length row per edge type it has, eave + rake and ridge + hip). It shows no verification
line, no drip edge or ridge cap variants, no parapet row (a parapet edge is drawn as an unspecified line), no "predominant pitch", no
chimney or lantern. An old `step_flashing` edge reads and is named "Sidewall flashing", an old `wall_flashing` edge "Headwall flashing" (the types are unchanged, the names follow the 0.6 words). `blocks`, `verification`, `from_planes` and `planes_only` stay in `extra` and are written back untouched; the removed keys inside an old `totals` (drip edge, ridge cap, predominant pitch, `complexity` and the rest) are not modelled and are NOT written back. "Ridge + hip" is never shown smaller than "ridge": an old or inconsistent `ridge_hip_ft` below the drawn ridge would make a cost sheet short of ridge cap, so the reader clamps it up.

### Label placement

Edge labels sit beside the edge, rotated to it, never upside down, on the side away from the roof
centroid first and the inner side second, sliding along the edge when the middle is taken. Because
the label is beside the edge and not on it, an edge may be shorter than its label: it needs to be
at least `LabelPlacer.shortEdgeFactor` (0.5) times the label width, and at least
`DiagramStyle.minLabelPx` pixels (default 6, at 1600 px wide). A label is hidden when the edge is
shorter than that, when it would leave the drawing area, overlap another label or touch any edge.
Edges on a hole outline are never labelled. Facet labels sit at the pole of inaccessibility (a port of Mapbox's
polylabel, ISC licence, in `lib/src/polylabel.dart`), shrink to fit, move off holes, and are
hidden only when no size fits.

Text is measured with Helvetica advance widths (`lib/src/metrics.dart`), so SVG, PDF and the
placer agree. Text outside Latin-1 needs a TrueType font for the PDF:
`scenesToPdf(scenes, fontTtf: bytes)`; without one it prints `?`.

## Example

```dart
final m = RoofMeasurement.parseAny(jsonDecode(body) as Map<String, dynamic>);
final rows = totalRows(m.model, const RoofLabels()); // the rows this roof has, in report order
print('${rows.first.label}: ${rows.first.value}');
final scenes = [
  LengthDiagram.build(m.model, layout: ReportLayout.compact),
  AreaDiagram.build(m.model, labels: RoofLabels.fromMap(strings)),
];
```

## Render

```
cd packages/bond_roof
dart run example/render_fixtures.dart [font.ttf]
```

Writes `<fixture>_<wide|compact>_<length|area|summary>.svg` and `<fixture>.pdf` to `tmp/render/`
(git-ignored) for every model fixture and every model inside an envelope (`fixtures/` and `fixtures/roof_engine/`), and prints edges,
labels placed and labels hidden per fixture and layout. On macOS, `qlmanage -t -s 900 -o <dir> file.svg` makes a PNG.

## Add a fixture

The reference input is the hand-written `fixtures/roof_engine/roof_measurement_0.7_sample.json` (see `fixtures/README.md`). A fixture of
the old shapes in `fixtures/` (shared with the Python side) is opened by `test/old_shapes_test.dart`, which builds all three scenes of
every roof or envelope JSON there in both layouts. A generated fixture must recompute to within 0.5 sq ft and 0.05 ft.

## Tests

`model_test.dart` (round trip, the 0.6 sample, old shapes, tolerant parser, errors), `totals_test.dart` (the 0.6 keys, null not zero, the
rows a roof has), `objects_test.dart` (chimney and lantern marks, legend rows, never a facet), `diagram_test.dart` (the sample: scene fits,
at most 30 percent of labels hidden, no label overlap or edge contact, well-formed SVG, legend and pitch labels), `old_shapes_test.dart`,
`measurement_test.dart` (envelope, `unknownEnvelopeKeys`), `format_test.dart`, `layout_test.dart` (polylabel, collision geometry, placer),
`pdf_test.dart`, `labels_test.dart` (every key, a Spanish map in both layouts), `flat_seams_test.dart`, `area_by_roof_type_test.dart`.

## Known limits

- At small wide-layout scene sizes (about 800 px wide and below) the legend columns can come close
  to each other; use `ReportLayout.compact` for phone width. Compact hides more labels (the plan is a
  quarter the size and labels are 14 px), so only the legend and totals are guaranteed.
- A facet label can have a hole outline cross the box between the sampled points; only hole
  vertices and edge crossings near the box are checked, not a chord spanning the whole box.
- `pitchLabel` of a non-finite rise prints "Flat".
- The pitch shown beside the whole number is the fitted value to the tenth; a roof with no pitched facet shows no pitch.
- An object is drawn as its `polygon` (the measured, possibly rotated footprint) when the service sends one, else as the axis-aligned `size_ft` rectangle (`[x, y]` feet). A mark shorter than 18 px is scaled about its centre.

## License

MIT, see `LICENSE` in this directory (Copyright (c) 2026 John Carnahan). The rest of the bond-factory
repository is MIT as well, except `services/roof_measure` (GPL-3.0-or-later), which this package does not depend on. Third-party notices: `lib/src/polylabel.dart` is a port of Mapbox polylabel under the ISC licence (notice in the file header).
