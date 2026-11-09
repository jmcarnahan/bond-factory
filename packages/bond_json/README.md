# bond_json

Null-safe readers for decoded JSON maps and UTC timestamp helpers. Pure Dart, no Flutter, no dependencies.

A missing key or `null` reads as `null` (an empty list for lists). A value of the wrong type throws `JsonShapeError`, so a contract break fails loudly instead of showing wrong data.

## Public API

| Name | What it does |
| --- | --- |
| `jstr(m, k)` | String or null |
| `jint(m, k)` | int from an int, any num (truncated) or a numeric string |
| `jnum(m, k)` | double from a num or a numeric string |
| `jbool(m, k)` | bool, no coercion |
| `jmap(m, k)` | string-keyed copy of a nested map |
| `jlist(m, k, f)` | list read element by element; missing or null gives `const []` |
| `jlistOf(v, f)` | the same for a top-level array |
| `jtime(m, k)` | ISO-8601 string to UTC `DateTime`; `Z`, offset and naive (taken as UTC) all work; ints throw |
| `jiso(t)` | UTC, millisecond precision, trailing `Z` |
| `enumByWire(values, wire, wireOf)` | enum member or null for an unknown string |
| `JsonShapeError` | `path`, `expected`, `actual` |

## Depend on it

```yaml
dependencies:
  bond_json:
    git:
      url: https://github.com/jmcarnahan/bond-factory.git
      ref: <full 40-char sha>
      path: packages/bond_json
```

Tags are labels only: pin the full SHA. For local work put a `path:` entry in a gitignored `pubspec_overrides.yaml`.

## Example

```dart
import 'package:bond_json/bond_json.dart';

enum Status { open, done }

class Task {
  Task.fromJson(Map<String, Object?> j)
      : title = jstr(j, 'title') ?? '',
        due = jtime(j, 'due'),
        status = enumByWire(Status.values, jstr(j, 'status'), (s) => s.name) ?? Status.open,
        tags = jlist(j, 'tags', (v) => v! as String);
  final String title;
  final DateTime? due;
  final Status status;
  final List<String> tags;
}
```

## Test

```
make -C packages/bond_json test
```
