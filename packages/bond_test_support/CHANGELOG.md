# Changelog

## 0.1.0 - unreleased
- Scaffold.
- `expectNoOverlays(tester)`: fails on dialogs, bottom sheets, snack bars, popup menus (button or open menu), a shown tooltip, and any animated or dismissible modal barrier. Matches by type-name fragments so the lib passes the no-popups gate.
- `setPhone` (390 x 844) and `setWideScreen` (1280 x 800): logical size plus pixel ratio, reset at teardown.
- `FakeCall<T>`: records arguments, serves queued results, a sticky result, or errors.
- `CannedResponses`, `CannedResponse`, `CannedHttpClient`, `RecordedRequest`: an `http.Client` that serves queued answers by method and path (the last answer repeats) and records requests. No match gives a 404 and is listed in `unmatched`.
- `pumpUntil` (finder, fake time) and `pumpUntilThat` (any condition), `pollUntil<T>` (real time), `Emissions<T>` (collects stream events with a bounded wait). Every wait fails with a readable message at its cap.
- `pumpApp(tester, child, {theme})`: MaterialApp plus Scaffold around the widget.
- Adds the `http` dependency (the canned client extends `http.BaseClient`).
- Not lifted: the seed's app API double, fixtures, auth controller overrides and PowerSync database helpers (app specific; they belong in the apps or in the sync adapter's own testing library).
