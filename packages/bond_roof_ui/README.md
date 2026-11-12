# bond_roof_ui

Flutter widgets that draw a `bond_roof` scene on a canvas and turn a roof model into a
printable three-page report (length diagram, area diagram, summary). Pure drawing: the geometry, labels and totals come from
`packages/bond_roof` (see `docs/contracts/roof_model.md`).

## Public API (`package:bond_roof_ui/bond_roof_ui.dart`)

- `RoofDiagramView(scene, {fit})`: a widget that paints a `Scene` with `ScenePainter`
  (a `CustomPainter`), scaled to fit. Text is baked into the scene, so labels are chosen when the
  scene is built.
- `RoofReportStrip({model | measurement, labels, filename, showActions, showTotals, onStatus})`:
  Print, Save PDF and Share PDF buttons with inline status, the totals table, then the length
  diagram, area diagram and summary. Under 600 px wide it builds the compact (400 x 500)
  scenes. Scenes are cached per model, labels and layout. No dialogs, snackbars or tooltips.
- `RoofTotalsTable(measurement, {labels})`: inline text rows for the totals, both drip edge and
  both ridge cap variants, the verification verdict with its first note, and the generated time.
- `RoofReport.pages(model, {style, labels, layout})`, `pdfBytes`, `printReport`, `saveReport`,
  `shareReport`: the scenes, the PDF (Letter landscape) and the hand-off to the OS print
  dialog or share sheet through package `printing`. Both are OS-owned surfaces, so they are
  allowed under the no-popups rule. `printReport` and `shareReport` also exist as top-level
  functions. On web, Save PDF and Share PDF both download the file.
- `RoofLabels` (from `bond_roof`): pass `RoofLabels.fromMap(strings)` as `labels` to translate
  everything; keys are `RoofLabels.keys`.
- `RoofUiTokens`: page size, breakpoint and the few layout constants.

The PDF embeds the bundled Roboto Regular (Apache 2.0, `assets/fonts/`) so output is the same
on every platform.

## Use from an app

A consumer must depend on BOTH `bond_roof` and `bond_roof_ui`: the UI barrel does not re-export
`RoofModel`, `RoofMeasurement` or `RoofLabels`, so import those from `package:bond_roof/bond_roof.dart`.

Inside this workspace, depend by path (the root `pubspec.yaml` resolves it):

```yaml
dependencies:
  bond_roof:
    path: ../../packages/bond_roof
  bond_roof_ui:
    path: ../../packages/bond_roof_ui
```

From another repository, pin the full 40-character commit SHA (tags are labels only):

```yaml
dependencies:
  bond_roof:
    git:
      url: https://github.com/jmcarnahan/bond-factory.git
      ref: <full 40-char sha>
      path: packages/bond_roof
  bond_roof_ui:
    git:
      url: https://github.com/jmcarnahan/bond-factory.git
      ref: <full 40-char sha>
      path: packages/bond_roof_ui
```

## Develop

```
flutter test            # widget test
make test-flutter       # from the repo root, with the demo app's tests
make gates              # no-popups gate
```

`demos/roof_demo` is the reference consumer.

## License

MIT, see `LICENSE` in this directory (Copyright (c) 2026 John Carnahan). The rest of the bond-factory
repository is MIT as well, except `services/roof_measure` (GPL-3.0-or-later), which this package does not depend on. Third-party notices: the Roboto font in `assets/fonts/` is Apache-2.0 (`Roboto_LICENSE.txt`). It depends on `bond_roof`, which is MIT as well.
