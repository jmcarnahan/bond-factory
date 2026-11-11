# bond_roof

Pure Dart (no Flutter). Parses the roof model JSON (`bond.roof_model/0.1`, see
`docs/contracts/roof_model.md`) and the service envelope (`bond.roof_model/0.2`), recomputes totals, and lays out three diagrams as
device-independent scenes that can be written to SVG or PDF or painted by a Flutter widget.

`dart test` and `dart analyze` need only the Dart SDK. No codegen: `fromJson` and `toJson` are
hand-written. No network access.

## API

| Import | Name | What it is |
|---|---|---|
| `bond_roof.dart` | `RoofModel.fromJson` / `toJson` | Parse and write the contract JSON. Throws `FormatException` starting with the JSON path (`edges[3].polygon: ...`) for structural errors. An unknown edge type, facet kind, block form or `lengths_ft` key is mapped (`unspecified`, by pitch, `flat`, `extraLengths`) and recorded in `RoofModel.parseNotes`. Unknown top-level keys (`origin`, `generated_at`, `debug`) survive a round trip in `extra`. |
| | `RoofMeasurement.parseAny(json)` | Reads a 0.2 envelope (model, 14 totals, verification, confidence, warnings and `warning_codes`) or wraps a bare 0.1 model as an unverified measurement. Unknown top-level keys survive in `extra`. |
| | `RoofTotalsVariants.of(totals)` | Takes the model's `RoofTotals` (`measurement.model.totals`) and returns drip edge (eave / eave + rake) and ridge cap (ridge / ridge + hip) from the ten length totals. `RoofEnvelopeTotals` carries the same four values as fields (`dripEdgeEaveFt`, `dripEdgeEaveRakeFt`, `ridgeCapRidgeFt`, `ridgeCapRidgeHipFt`) and a `.variants` getter. |
| | `RoofLabels` | Every user-visible string with English defaults; `RoofLabels.fromMap(map)` overrides by `RoofLabels.keys`, `{name}` placeholders in templates. |
| | `ReportLayout` | `wide` (1600 x 1000, 3-column legend) or `compact` (400 x 500, 2 columns, text sized for a phone card) for the three builders. |
| | `RoofModel.recomputeTotals()` | Totals from facets and edges, same rules as the contract. |
| | `RoofModel.bounds` | Bounding box of all geometry, feet. |
| | `feetInches`, `wholeFeet`, `sqft`, `pitchLabel` | Number formats: `209ft 8in`, `35`, `2,121`, `Flat` / `4/12` / `4.5/12`. |
| | `LengthDiagram.build(model, {labels, layout})` | Edges by type, whole-foot labels, legend of totals, compass, footer. |
| | `AreaDiagram.build(model, {labels, layout})` | Facet outlines, pitch and area per facet, dashed holes, eight totals. |
| | `SummaryBlock.build(model, {width, labels, layout})` | Text report; height grows with content. |
| | `DiagramStyle` | Palette and sizes (`DiagramStyle.report` is the contract palette). |
| | `Scene`, `LinePrim`, `PolyPrim`, `TextPrim` | The drawing primitives. Logical pixels, y down, ARGB colours, text centred vertically on its anchor point. |
| | `sceneToSvg(scene)` | SVG string. |
| `roof_pdf.dart` | `scenesToPdf(scenes, {fontTtf, title, labels})` | One PDF page per scene, 792 pt wide. Separate import so web apps do not pull in `package:pdf`. |

`Scene.hiddenLabels` counts length labels (or facet labels) left off; `Scene.placedLabels` counts
the ones drawn.

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
final v = RoofTotalsVariants.of(m.model.totals); // same numbers as m.totals.variants
print('${v.dripEdgeEaveFt} / ${v.dripEdgeEaveRakeFt} ft drip edge');
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
(git-ignored) for every model fixture and every model inside a 0.2 envelope, and prints edges,
labels placed and labels hidden per fixture and layout. On macOS, `qlmanage -t -s 900 -o <dir> file.svg` makes a PNG.

## Add a fixture

Drop a `bond.roof_model/0.x` model or envelope JSON file in `fixtures/` (repo root, shared with the services) or in
`packages/bond_roof/test/fixtures/`. Every test and the render script pick up all `*.json` files
whose `schema` or `contract` matches; other files are skipped. A generated fixture must recompute to within
0.5 sq ft and 0.05 ft; a `source.method: "manual"` model gets the looser tolerances in
`test/model_test.dart`.

## Tests

`test/model_test.dart` (round trip, totals, errors), `format_test.dart`, `layout_test.dart`
(polylabel, collision geometry, placer), `diagram_test.dart` (every fixture: scene fits, at most
30 percent of labels hidden, no label overlap or edge contact, well-formed SVG), `pdf_test.dart`, `measurement_test.dart`, `totals_variants_test.dart`, `labels_test.dart` (every key, a Spanish map in both layouts), `tolerant_parser_test.dart`.

## Known limits

- At small wide-layout scene sizes (about 800 px wide and below) the legend columns can come close
  to each other; use `ReportLayout.compact` for phone width. Compact hides more labels (the plan is a
  quarter the size and labels are 14 px), so only the legend and totals are guaranteed.
- A facet label can have a hole outline cross the box between the sampled points; only hole
  vertices and edge crossings near the box are checked, not a chord spanning the whole box.
- `pitchLabel` of a non-finite rise prints "Flat".
- Predominant pitch is a half-pitch bucket (flat is 0); ties go to the lower pitch.
