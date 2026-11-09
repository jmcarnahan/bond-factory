# bond-factory pins (copy this file into the app as `docs/sdk/sdk-pins.md`)

Every bond module the app imports, the commit it is pinned to, and any patch the app carries on top. Every bond
dependency in an app is pinned to the same SHA, so the SHA column holds one value for every module the app uses.
Fill in a row only for modules the app imports; delete the rest. Update this file in the same commit as the pin.

| Module | SHA (40 chars) | Date pinned | Local patches |
|---|---|---|---|
| bond_json | | | |
| bond_api | | | |
| bond_test_support | | | |
| bond_ui | | | |
| bond_auth | | | |
| bond_auth_firebase | | | |
| bond_sync | | | |
| bond_sync_powersync | | | |
| bond_tasks | | | |
| bond_tasks_ui | | | |
| bond_connections | | | |
| bond_connections_ui | | | |
| bond_service_kit | | | |
| bond_storage | | | |
| bond_auth_py | | | |
| bond_jobs | | | |
| bond_sync_py | | | |
| bond_oauth | | | |
| bond_signin (Python lib) | | | |
| bond_signin (Dart) | | | |
| bond_signin_ui | | | |
| bond_calendar | | | |
| bond_tasks_py | | | |

Rules:
- A local patch names the file, the reason and the upstream issue or PR. No patch lives longer than one upgrade.
- Divergence belongs in the app's adapters, not in a patched copy of a module.
- Remove `pubspec_overrides.yaml` and editable Poetry paths before committing the app's lockfiles.
