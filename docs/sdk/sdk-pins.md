# bond-factory pins (copy this file into the app as `docs/sdk/sdk-pins.md`)

Every bond-factory module the app imports, the commit it is pinned to, and any patch the app carries on top.
All Dart refs share one SHA. Update this file in the same commit as the pin change.

| Module | SHA (40 chars) | Date pinned | Local patches |
|---|---|---|---|
| bond_json | `<sha>` | YYYY-MM-DD | none |
| bond_api | `<sha>` | YYYY-MM-DD | none |
| bond_ui | `<sha>` | YYYY-MM-DD | none |
| bond_storage | `<sha>` | YYYY-MM-DD | none |

Rules:
- A local patch names the file, the reason and the upstream issue or PR. No patch lives longer than one upgrade.
- Divergence belongs in the app's adapters, not in a patched copy of a module.
- Remove `pubspec_overrides.yaml` and editable Poetry paths before committing the app's lockfiles.
