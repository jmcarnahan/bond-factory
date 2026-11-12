# Migrating to bond_json

Null-safe JSON readers and UTC timestamp helpers (`packages/bond_json`, pure Dart). Legend: `docs/migration/README.md`.

## 1. What it replaces

| App | Goes away or shrinks | Stays app-side |
|---|---|---|
| A | `flutterui/packages/avalon_core/lib/src/models/crew.dart:252` `parseServerInstant` (45 call sites), the copy in `crew_view/breaks_view.dart:59`, 8 `DateTime.parse` calls in `models/` | all model classes |
| S | nothing shared today (readers live per file; web and phone models differ) | all models; adopt for new code only |
| P | `flutterui/packages/pt_core/lib/src/models/json_util.dart` (68 lines) shrinks to a 15-line shim | `JsonEquatable`, `jmaps`, `jstrings`, `jints` (not lifted) |

## 2. The adapter

Signatures differ from P's file: bond readers take `(map, key)`, return null for a missing key and
throw `JsonShapeError` on a wrong type. P's readers take a value, return a default and never throw. P keeps
its tolerant policy in the shim, so its 18 importing files compile unchanged:

```dart
import 'package:bond_json/bond_json.dart' as b;

DateTime? jtime(Object? v) {
  try {
    return b.jtime({'t': v}, 't');
  } on b.JsonShapeError {
    return null; // tolerant: a bad value reads as absent
  }
}

String? jiso(DateTime? t) => t == null ? null : b.jiso(t);

T enumByWire<T extends Enum>(List<T> values, String? wire, T unknown, String Function(T) wireOf) =>
    b.enumByWire(values, wire, wireOf) ?? unknown;
```

A replaces `parseServerInstant(String? s)` with `jtime({'t': s}, 't')` at 45 sites, or keeps a one-line
wrapper named `parseServerInstant` and moves call sites later.

## 3. Call-site changes

| Old | New |
|---|---|
| A `parseServerInstant(s)` | `jtime({'t': s}, 't')` or `jtime(json, 'key')` |
| P `jstr(v, '')` (229 uses) | `jstr(json, 'k') ?? ''` (new code), shim keeps old form |
| P `jstrOrNull(v)`, `jintOrNull(v)`, `jdouble(v)` | `jstr(json, 'k')`, `jint(json, 'k')`, `jnum(json, 'k')` |
| P `jlist(v, f)` over maps | `jlist(json, 'k', (e) => f(jmap({'e': e}, 'e')!))`, or `jlistOf` for a top-level array |

Find them: `grep -rnE "parseServerInstant\(" flutterui` (A), `grep -rlE "json_util" flutterui` (P).

## 4. Data

None. Wire format is unchanged. `jiso` now writes milliseconds (`2026-11-08T10:30:00.000Z`).

## 5. Acceptance

- `flutter test` and `flutter analyze` in each edited package (A: `avalon_core`, P: `pt_core`).
- A test that feeds `jtime` an offset string (`+02:00`), a naive string and a date-only string and expects UTC.
- Run the suites under two time zones (the CI job uses `TZ=America/Los_Angeles`); any failure is a local
  `toLocal()` assumption.

## 6. Known gaps (behaviour the module dropped)

- Tolerant defaults: a wrong type throws instead of reading as a fallback. P keeps tolerance in its shim.
- `jint('12')` now returns 12 (P returned its fallback); `jint(1.9)` truncates to 1 as before.
- `jtime` throws on an integer (epoch) and on a string that is not a timestamp; P returned null (its shim keeps that).
- `jiso` writes 3 fractional digits; P printed microseconds when present.
- Not lifted: `JsonEquatable`, `jmaps`, `jstrings`, `jints`, the `unknown` argument of `enumByWire`.

## 7. Adoption-gaps changes
- `jtimeOrNull(m, k)` reads like `jtime` but never throws: a missing, null, empty, non-String or malformed value is null. Use it where a bad timestamp should read as "unknown".
- Bug fix: `jtime` and `jtimeOrNull` now reject impossible calendar dates and times. Before, Dart rolled them over to the next valid date. Rejected now: a month outside 1-12, a day past the month's end (leap years respected), an hour above 23 (so `24:00` is out), a minute above 59 and a second above 59 (so the leap second `23:59:60` is out; it used to read as the next minute). The check covers the extended form (`2026-02-30T10:00Z`), the basic form (`20260230T101010Z`) and an hour-only time (`2026-11-08T25`). A year with a sign or more than four digits (`-2026-...`, `10000-...`) is not checked. `jtime` throws `JsonShapeError` for them. A leap day (2028-02-29) still reads. If an adopter's data carried such values, expect the new throw (or null with `jtimeOrNull`).
