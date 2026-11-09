# Migrating to bond_test_support

Widget-test helpers (`packages/bond_test_support`, Flutter): `expectNoOverlays`, `setPhone`, `setWideScreen`,
`FakeCall<T>`, `CannedHttpClient`, `pumpUntil`, `pollUntil`, `Emissions`, `pumpApp`. Legend: `docs/migration/README.md`.

## 1. What it replaces

| App | Moves out | Stays app-side |
|---|---|---|
| A | slices of `flutterui/packages/avalon_core/lib/testing.dart` (5,312 lines): `setWideScreen` :5259, `setPhone` :5262, `expectNoOverlays` :5274; its self-test `test/testing_helpers_test.dart` 57 | `FakeCall` :57 (a call record, not the same thing), `FakeApi` :176, `FakeIdTokenSource` :5099 (goes to `bond_auth`), auth overrides, DB helpers |
| P | the same slices of `flutterui/packages/pt_core/lib/testing.dart` (1,279); `test/testing_helpers_test.dart` 104 | `FakeApi`, fixtures, controller overrides |
| S | phone `mobile/crm_proposals/test/test_host.dart:19` `setPhone` (of 56 lines); web `flutterui/test/test_utils.dart:24` `setWideScreen` (of 86) | `host()`, `FakeAuthController`, `skipOrFailInCi`; `test/sync/sync_test_db.dart` 196 and `_fakes/fake_sync_transport.dart` 61 go to the sync packages |

## 2. The adapter

Keep every `import 'package:avalon_core/testing.dart'` (295 in A) working by re-exporting from the old file.
Hide the two names whose behaviour differs and redefine them. This block replaces the moved helpers in A's and P's `testing.dart`:

```dart
import 'package:bond_test_support/bond_test_support.dart' as bts;
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

export 'package:bond_test_support/bond_test_support.dart' hide FakeCall, setWideScreen;

/// The seed's desktop window was 1280 x 900; bond's default is 1280 x 800.
void setWideScreen(WidgetTester tester) => bts.setWideScreen(tester, size: const Size(1280, 900));
```

`avalon_core` already imports `flutter_test` from `lib/`, so `bond_test_support` is a normal dependency of the
core package for now; moving `testing.dart` out of `lib/` is a separate cleanup. S keeps its own shims:

```dart
void setPhone(WidgetTester tester) => bts.setPhone(tester, dpr: 3); // test_host.dart rendered at 3x
```

## 3. Call-site changes

| Old | New | Find |
|---|---|---|
| `expectNoOverlays(tester);` (A 1,422, P 357) | `await expectNoOverlays(tester);` (now returns a `Future`) | `grep -rn "expectNoOverlays(" flutterui \| grep -v await` |
| `setPhone(tester)` (A 98, P 10, S 71) | unchanged: 390 x 844 at dpr 1; S passes `dpr: 3` | |
| `setWideScreen(tester)` (A 85, P 9, S 473) | unchanged through the shim above | |
| a hand-rolled canned `http.Client` | `CannedHttpClient(CannedResponses()..json('GET', '/x', {...}))` | |
| a `while (...) await tester.pump(...)` loop | `await pumpUntil(tester, find.text('Done'))` (fails after 5 s with a message) | `grep -rn "pump(const Duration" flutterui` |
| bond_ui tests | `pumpApp(tester, w, theme: BondTheme.build(BondTokens.fallback))` | |

`FakeCall<T>` is a scripted stub (`returns`, `returnsInOrder`, `throwsOnce`, `throwsAlways`, `call`); do not
rename A's record class to it. `CannedHttpClient` replaces nothing in A or P: their `FakeApi` stays.

## 4. Data

None. Add `bond_test_support` under `dev_dependencies` of each package that only uses it in `test/`.

## 5. Acceptance

- `flutter test` in every package whose `test/` imports `testing.dart` (A: `avalon_core`, `avalon_ui`,
  `avalon_screens`, `apps/crew_mobile`, `apps/office_web`; P: every package or app whose `test/` imports it).
- `flutter analyze` clean: `unawaited_futures` flags every missed `await`.
- The moved self-tests (`testing_helpers_test.dart`) are deleted; the module's own tests cover them.

## 6. Known gaps

- `expectNoOverlays` matches type-name fragments. It no longer flags `Drawer`, `MaterialBanner` or a closed
  `Tooltip` widget (A's list did); only a shown tooltip bubble counts. Keep a local check if the app relies on those.
- The tooltip check relies on two private Flutter class names; the module's self-test fails on a Flutter upgrade that renames them.
- Not lifted: `FakeApi`, fixtures, `FixedAuthController`, `signedInAs`, PowerSync database helpers, `FakeIdTokenSource`.
