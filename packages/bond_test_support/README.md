# bond_test_support

Test host, fakes and pump helpers for bond Flutter package tests. A library package: depend on it from `dev_dependencies` only.

## Public API

| Name | What it does |
| --- | --- |
| `expectNoOverlays(t)` | fails when a dialog, sheet, snack bar, popup menu, shown tooltip or popup barrier is on screen |
| `setPhone(t, {dpr, size})` | 390 x 844 logical pixels by default; reset at teardown |
| `setWideScreen(t, {size})` | 1280 x 800 logical pixels by default; reset at teardown |
| `pumpApp(t, child, {theme})` | MaterialApp plus Scaffold around `child` |
| `pumpUntil(t, finder, {timeout})` | pumps 50 ms frames until the finder matches; fails with a message at the cap (fake time) |
| `pumpUntilThat(t, ok, {what, timeout})` | the same for any condition |
| `pollUntil<T>(probe, {timeout})` | real-time polling until the probe returns non-null |
| `Emissions<T>(stream)` | collects `values`, `errors`, `done`; `until`, `take(n)`, `untilDone` with a bounded wait |
| `FakeCall<T>` | records calls; `returns`, `returnsInOrder`, `throwsOnce`, `throwsAlways` |
| `CannedHttpClient` | `http.Client` serving `CannedResponses` by method and path; records `requests` |

## Depend on it

```yaml
dev_dependencies:
  bond_test_support:
    git:
      url: https://github.com/jmcarnahan/bond-factory.git
      ref: <full 40-char sha>
      path: packages/bond_test_support
```

Pin the full SHA; tags are labels only.

## Example

```dart
testWidgets('opens nothing over the page', (t) async {
  setPhone(t);
  await pumpApp(t, const MyScreen());
  await pumpUntil(t, find.text('Ready'));
  await expectNoOverlays(t);
});

test('client talks to the canned server', () async {
  final http = CannedHttpClient()..responses.json('GET', '/me', {'id': 1});
  final api = ApiClient(baseUrl: Uri.parse('https://x.test'), http: http);
  expect(await api.getJson('/me'), {'id': 1});
  expect(http.requests.single.path, '/me');
});
```

`pollUntil` and `Emissions.until` wait in real time: inside `testWidgets` wrap them in `tester.runAsync`.

## Test

```
make -C packages/bond_test_support test
```
