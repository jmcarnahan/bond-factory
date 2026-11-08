# roof_demo

A single-screen Flutter app (web and iOS) that exercises `bond_roof` and `bond_roof_ui`
end to end. Not shipped.

What it does:

- Address field, a segmented control for the method (LiDAR, LiDAR + agent, Solar + agent)
  and a Measure button that POSTs `{"address", "method"}` to the Python service
  (`services/roof_measure`, FastAPI on port 8011) and renders the returned roof model.
- Fixture chips that load bundled copies of `fixtures/*.json` (roof-model schema only), so
  the app works with no service running. Chips for fixtures the live service offers are
  added when it is reachable.
- An inline report: a collapsible raw-model panel, Print and Save PDF (through
  `bond_roof_ui`), the length diagram and the area diagram. Progress and errors are inline
  text. No popups, no dialogs, no toasts.

## Run

From the repo root:

```
make demo-web      # flutter run -d chrome
make build-web     # release build in build/web; serve it with python3 -m http.server
make demo-ios      # flutter run on the booted iOS simulator
```

Both targets first run `tool/sync_fixtures.sh` (also `make sync-fixtures`), which copies the
roof-model fixtures into `assets/fixtures/`. Re-run it whenever `fixtures/` changes.

The service URL defaults to `http://localhost:8011`; override at build or run time with
`--dart-define=ROOF_SERVICE=http://host:port`. Start the service with `make serve` in
`services/roof_measure`.

## Status (POC)

- Web build and iOS simulator build verified; the web app was driven in a browser.
- Print and Save PDF are wired through `printing` but were not exercised by hand on iOS.
- `flutter test` covers the page's controls and the service client's fixture-list parsing.
