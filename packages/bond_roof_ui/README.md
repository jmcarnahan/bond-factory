# bond_roof_ui

Flutter widgets that draw a `bond_roof` scene on a canvas and turn a roof model into a
printable three-page report (length diagram, area diagram, summary). Pure drawing: the geometry, labels and totals come from
`packages/bond_roof` (see `docs/contracts/roof_model.md`).

## Public API (`package:bond_roof_ui/bond_roof_ui.dart`)

- `RoofDiagramView(scene, {fit})`: a widget that paints a `Scene` with `ScenePainter`
  (a `CustomPainter`), scaled to fit.
- `RoofReport.pages(model, {style})`: the length diagram, the area diagram and the summary block as three
  `Scene`s at `RoofReport.pageWidth` x `RoofReport.pageHeight` (1650 x 1275 px, US Letter
  landscape at 150 dpi).
- `printReport(model, ...)` and `shareReport(model, ...)`: build the PDF with
  `bond_roof`'s `scenesToPdf` and hand it to the OS print dialog or share sheet through
  package `printing`. Both are OS-owned surfaces, so they are allowed under the no-popups rule.
- `RoofReportStrip(model, {filename})`: an inline row with Print and Save PDF buttons and
  inline status text (no toasts, no dialogs).
- `RoofUiTokens`: page size and the few layout constants.

The PDF embeds the bundled Roboto Regular (Apache 2.0, `assets/fonts/`) so output is the same
on every platform.

## Use from an app

Inside this workspace, depend by path (the root `pubspec.yaml` resolves it):

```yaml
dependencies:
  bond_roof_ui:
    path: ../../packages/bond_roof_ui
```

From another repository, pin a commit:

```yaml
dependencies:
  bond_roof_ui:
    git:
      url: <bond-factory git url>
      path: packages/bond_roof_ui
      ref: <commit sha>
```

## Develop

```
flutter test            # widget test
make test-flutter       # from the repo root, with the demo app's tests
make gates              # no-popups gate
```

`demos/roof_demo` is the reference consumer.
