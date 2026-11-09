# sdk_example

Reference FastAPI app wiring every bond Python lib, in fake mode (no network, no secrets).
Phase 1 state: skeleton only. It serves `GET /health` and discovers route modules from `sdk_example/routes/`;
the lib routes (auth, sync, connections, tasks, jobs) land in phases 2 and 3.

```
make -C services/sdk_example test
make serve-example        # uvicorn on :8012, built through the create_app factory
```

Settings come from `SDK_EXAMPLE_*` variables (see `sdk_example/settings.py`). With none set the app starts in
fake mode and logs one warning. Real mode needs `SDK_EXAMPLE_AUTH_SECRET`, and a `*` CORS origin is refused.

## Copying this into an app

Default to real mode. Fake mode (mock identities, demo auth, generated keys in `out/`) exists so the example
and its tests run with no setup. An app should fail fast on a missing secret, as `Settings.from_env()` does
for real mode, and never ship the fake defaults.
