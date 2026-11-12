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
| bond_notify_py | | | |
| bond_push_py | | | |
| bond_capture_py | | | |
| bond_notify | | | |
| bond_notify_ui | | | |
| bond_push | | | |
| bond_push_apple | | | |
| bond_auth_secure_storage | | | |
| bond_tasks_notifications | | | |
| bond_tasks_powersync | | | |
| bond_notify_powersync | | | |

The TODO modules (`bond_tasks*`, `bond_notify*`, `bond_push`, `bond_push_py`, `bond_capture_py`) are first pinned at `fe57595d2530dfd0933dba81971dd021ec472ead`.

The adoption-gap seams (`bond_api` `endsSession` and per-call timeouts, `bond_tasks_py` `prepare`, `extra_where`, `labels`, `grandfather_before`, app-set work-day defaults and `draft_for`, `bond_notify_py` `get_owned`, `bond_sync_py` `now` and `close_sessions`, `bond_calendar` `Forbidden` and `reminder_off`, `bond_storage` redirect grants, `bond_jobs` `run_schedule`, `bond_service_kit` `fake_clock_router`, `code_aliases` and callable rates, `bond_push_py` live check, `bond_tasks` and `bond_tasks_powersync` extras, and the new `bond_push_apple` and `bond_auth_secure_storage` packages) are first available at the merge commit of this branch, to be filled when it merges: `<this branch's merge commit>`.

Rules:
- A local patch names the file, the reason and the upstream issue or PR. No patch lives longer than one upgrade.
- Divergence belongs in the app's adapters, not in a patched copy of a module.
- Remove `pubspec_overrides.yaml` and editable Poetry paths before committing the app's lockfiles.
