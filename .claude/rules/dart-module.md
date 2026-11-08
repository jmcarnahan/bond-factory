---
paths: ["packages/**", "demos/**"]
---
# Dart / Flutter modules

- Map source to test: `lib/src/x.dart` -> `test/x_test.dart`. When unsure: `grep -rl "<ClassName>" test/`.
- Run one file: `make -C <module> test T=test/x_test.dart`. Never the whole suite mid-task.
- `make -C <module> analyze` is fast; run it before handing back.
- Lints: flutter_lints plus the six extra rules in the root analysis_options.yaml. Do not weaken them per module.
- Hand-write `fromJson` / `toJson`. No build_runner, freezed or json_serializable.
- No popups, dialogs, modal sheets or snackbars; show state inline. Check with `make gates`.
- Modules sit at depth 2; a sibling dependency is a pubspec `path:` entry and nothing else.
- A `bond_<x>` core package must not import Flutter (`package:flutter`, `dart:ui`).
- Public API change: update the barrel file and the module CHANGELOG.md in the same commit.
- Keep source files under about 300 lines; split when next touched.
- Fixtures: shared in `../../fixtures/` (<= 100 KB), private in `<module>/test/fixtures/`.
