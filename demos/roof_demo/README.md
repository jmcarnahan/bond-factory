# roof_demo

A single-screen Flutter app (web and iOS) that exercises `bond_roof` and `bond_roof_ui` end to end. Not shipped. It reads the bundled
fixtures only: no service is called, no address is typed, nothing is measured.

What it does:

- Fixture chips that load bundled copies of `fixtures/*.json` and `fixtures/roof_engine/*.json` (bare models and envelopes). Start with
  `roof_measurement_0.6_sample`, the hand-written 0.6 envelope; the older ones show how an envelope of an old shape opens and draws less.
- An EN/ES switch that shows the label-override seam with a sample Spanish map (a value for every `RoofLabels.keys` key).
- An inline report: a collapsible raw-model panel, Print and Save PDF (through `bond_roof_ui`), the totals table, the length diagram, the
  area diagram and the summary. Errors are inline text. No popups, no dialogs, no toasts.

## Run

From the repo root:

```
make demo-web      # flutter run -d chrome
make build-web     # release build in build/web; serve it with python3 -m http.server
make demo-ios      # flutter run on the booted iOS simulator
```

Both targets first run `tool/sync_fixtures.sh` (also `make sync-fixtures`), which copies the roof-model fixtures into `assets/fixtures/`.
Re-run it whenever `fixtures/` changes.

## Tests

`flutter test` covers the page's controls (no Measure button), picking the 0.6 sample and an old envelope, the EN/ES switch, and the
Spanish sample's keys.
