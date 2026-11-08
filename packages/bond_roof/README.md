# bond_roof

Pure Dart (no Flutter). Parses the roof model JSON (`bond.roof_model/0.1`, see
`docs/contracts/roof_model.md`), recomputes totals, and lays out three Roofr-style diagrams as
device-independent scenes that can be written to SVG or PDF or painted by a Flutter widget.

`dart test` and `dart analyze` need only the Dart SDK. No codegen: `fromJson` and `toJson` are
hand-written. No network access.

## API

| Import | Name | What it is |
|---|---|---|
| `bond_roof.dart` | `RoofModel.fromJson` / `toJson` | Parse and write the contract JSON. Throws `FormatException` starting with the JSON path (`edges[3].type: ...`). Unknown top-level keys (`origin`, `generated_at`, `debug`) survive a round trip in `extra`. |
| | `RoofModel.recomputeTotals()` | Totals from facets and edges, same rules as the contract. |
| | `RoofModel.bounds` | Bounding box of all geometry, feet. |
| | `feetInches`, `wholeFeet`, `sqft`, `pitchLabel` | Roofr number formats: `209ft 8in`, `35`, `2,121`, `Flat` / `4/12` / `4.5/12`. |
| | `LengthDiagram.build(model)` | Edges by type, whole-foot labels, legend of totals, compass, footer. |
| | `AreaDiagram.build(model)` | Facet outlines, pitch and area per facet, dashed holes, eight totals. |
| | `SummaryBlock.build(model, width:)` | Text report; height grows with content. |
| | `DiagramStyle` | Palette and sizes (`DiagramStyle.roofr` is the contract palette). |
| | `Scene`, `LinePrim`, `PolyPrim`, `TextPrim` | The drawing primitives. Logical pixels, y down, ARGB colours, text centred vertically on its anchor point. |
| | `sceneToSvg(scene)` | SVG string. |
| `roof_pdf.dart` | `scenesToPdf(scenes, {fontTtf, title})` | One PDF page per scene, 792 pt wide. Separate import so web apps do not pull in `package:pdf`. |

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

## Render

```
cd packages/bond_roof
dart run example/render_fixtures.dart [font.ttf]
```

Writes `<fixture>_length.svg`, `<fixture>_area.svg`, `<fixture>_summary.svg` and `<fixture>.pdf`
to `example/out/` (git-ignored) for every model fixture, and prints edges, labels placed and
labels hidden per fixture. On macOS: `rsvg-convert -w 1600 file.svg -o file.png`.

## Add a fixture

Drop a `bond.roof_model/0.1` JSON file in `fixtures/` (repo root, shared with the services) or in
`packages/bond_roof/test/fixtures/`. Every test and the render script pick up all `*.json` files
whose `schema` matches; other schemas are skipped. A generated fixture must recompute to within
0.5 sq ft and 0.05 ft; a `source.method: "manual"` fixture gets the looser tolerances in
`fixtures/README.md`.

## Tests

`test/model_test.dart` (round trip, totals, errors), `format_test.dart`, `layout_test.dart`
(polylabel, collision geometry, placer), `diagram_test.dart` (every fixture: scene fits, at most
30 percent of labels hidden, no label overlap or edge contact, well-formed SVG), `pdf_test.dart`.

## Known limits

- At small scene sizes (about 800 px wide and below) the legend columns can come close to each
  other; the plan itself still fits.
- A facet label can have a hole outline cross the box between the sampled points; only hole
  vertices and edge crossings near the box are checked, not a chord spanning the whole box.
- `pitchLabel` of a non-finite rise prints "Flat".
- Predominant pitch is a half-pitch bucket (flat is 0); ties go to the lower pitch.
