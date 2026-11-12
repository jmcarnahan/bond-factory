# Changelog

## 0.1.0 - unreleased
- Scaffold.
- Tasks and inbox routes are the libs' router factories (`routes/task_routers.py`); `routes/tasks.py`, `task_today.py` and `notices.py` are gone, the wire is unchanged. `POST /tasks/parse` takes `rich` (default false).
- Connections: native-app flow (`start?mode=native`, cookie-less `/go` and callback for native states, `POST
  /connections/{provider}/redeem`); `SDK_EXAMPLE_NATIVE_REDIRECTS` (default `sdkdemo://connections`).
- Direct sign-in: `signin_wiring.py` (library objects, cookies, router and well-known mounts), `directory.py` (the
  `UserDirectory` over `users`), `scope_policy.py`; `users` gains `identity_provider`, `identity_subject` (unique pair)
  and `allow_password`; new tables `auth_sessions` and `oauth_handoffs` (migration `0003_signin`).
- `/auth/refresh`, `/auth/logout` and `/auth/providers` are now the library's; `/auth/firebase` is break-glass only
  (`SDK_EXAMPLE_BREAKGLASS=1`, rows with `allow_password`); `/auth/demo` and break-glass issue refresh sessions
  (`delivery: "body"` for phones); fake-mode `POST /auth/simulate-reuse`.
- Breaking: `GET /connections` answers `{connections, wanted}` (was a bare array); `start` takes `set`; a native
  `start` needs `device_challenge` and `redeem` needs `device_secret` (hand-offs live in `oauth_handoffs`); the
  provider error `access_denied` reads `consent_declined`; connect scopes come from the policy, never `GOOGLE_DEFAULT`.
- Hardening: Origin rule for cookie-authenticated mutations (`origin_rule.py`); daily `signin_prune` job; real mode has no
  localhost defaults (allowlist required, CORS origins checked against it); startup refuses a database behind head, a
  `fake*` provider outside fake mode, and fake mode on https (`SDK_EXAMPLE_ALLOW_FAKE_PUBLIC=1` to allow); phone connect
  needs an account bound by sign-in; `demo@example.com` is the seeded break-glass row (`allow_password`).
- `SDK_EXAMPLE_CONNECTIONS=0` for sign-in only (`providers_wiring.py` builds the providers for both modules); real
  mode no longer defaults the native scheme; `directory.find_invite` takes the new `subject=` argument.
- Fake consent page is an identity picker with scope-set boxes (`sdk-consent-*` ids). New settings
  `SDK_EXAMPLE_SIGNIN_PROVIDERS`, `_PUBLIC_BASE` (also the connect callback base), `_NATIVE_RETURN_BASE`,
  `_NATIVE_SCHEMES`, `_BREAKGLASS`, `BOND_APPLE_APP_IDS`, `BOND_ANDROID_APPS`.
- TODO checklist (migration `0005_todo_tables`): tables for user settings, link index, notice ledger and outbox,
  inbox notices and push devices; `tasks.remind_at` and `reminded_at` are dropped. Routes: `GET /tasks/today`,
  `GET|PUT /tasks/settings`, `GET /tasks/links/search`, `POST /tasks/parse`, `GET /notices`,
  `POST /notices/{id}/read|dismiss|act`, `POST /notices/read-all`, `POST /push/devices`,
  `DELETE /push/devices/{device_id}`, `POST|GET /capture/events`; task reads take `time_zone` and measure `overdue`
  against the clock. `POST /jobs/tick` now also runs the sweep (`sweep`, `deliver` in the answer). Fake-mode
  helpers: `GET /fake/push/sent`, `PUT /fake/capture`, `PUT /fake/capture/limit`. The sync host gains `notices` and
  `push_devices`, and task writes over sync keep the inbox in step. `scripts/sweep_interval.py` runs the sweep with
  no jobs table. SQLite engines are prepared with `sqlite_savepoint_setup`.
- Adoption-gap seams (2026-11-12). Migration `0006_settings_follow_default`: `task_user_settings.start_of_day`, `end_of_day`
  and `lead_minutes` are nullable (NULL = follow the app default); the upgrade sets stored values equal to 08:00, 17:00 and 60 to NULL, and the downgrade fills them back first. The default
  work day is `SDK_EXAMPLE_START_OF_DAY`, `_END_OF_DAY`, `_LEAD_MINUTES`, one `UserPrefs` on `app.state.default_prefs` passed to
  every place preferences are built; `GET|PUT /tasks/settings` answer `overridden`, and a null field resets. `/fake/clock` is
  the kit's `fake_clock_router` (`clock_pin.py`); the sync upload and the token report the app clock; the 503 for a database
  outage comes from the kit middleware, not the route. `GET /tasks` takes `status=cancelled|active`; link labels are read from
  the contact directory at response time; task writes pass a `prepare` rule on REST and sync (`todo_wiring.owner_edits_closed`);
  the notice `act` route calls `get_owned` first; the calendar mirror's `draft_for` adds the first link to the event body;
  `scripts/sweep_interval.py` runs `bond_jobs.run_schedule` (sweep and prune as two entries) and
  `SDK_EXAMPLE_GRANDFATHER_BEFORE` reaches `sweep_due`. Existing tests changed: the settings route tests expect
  `overridden`, the two head-revision checks expect `0006`, and the old `prune_due` test checks the prune entry instead.
- Breaking: the in-memory notices list, `GET /tasks/notices`, the `task_reminder` job and `AppScheduler` are gone; the
  `today` query parameter no longer decides `overdue` (the clock and the viewer zone do).
