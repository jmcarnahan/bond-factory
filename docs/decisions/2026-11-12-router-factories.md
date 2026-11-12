# 2026-11-12 Router factories in two Python libs

Status: accepted. Dated, append-only.

## Context

Every adopting app copied the example's task and inbox routes (about 290 lines): the same handlers, the same query
filters, the same error bodies. The copies drifted. The routes need the web framework, and the libs had so far kept
the framework out of their core import list.

## Decisions

- `bond_tasks_py.routes.make_tasks_router` and `bond_notify_py.routes.make_notices_router` return an `APIRouter`. The app
  mounts it with `include_router`. The wire is the one the example already had: same paths, status codes and error bodies.
- fastapi is the optional extra `http` of both libs. The package `__init__` never imports the routes module, so
  `import bond_tasks_py` still pulls in no framework and each lib's `tests/test_boundary.py` keeps its import list.
  An app that wants the routes imports `bond_tasks_py.routes`.
- The factories hold no app state. They take callables: `session_scope` (a context manager factory that commits on
  exit), `user_dep`, `now`, and hooks. Tasks: `after_write(session, task, now, before)`, `snapshot`,
  `after_commit(background, task)`, `after_delete`, `after_delete_commit`, `link_hook`, `labels`, `names`,
  `user_exists`, `prefs`, `defaults`, `on_recomputed`, `read_all_dep`, `write_dep`, `prepare`, `extra_where_for`,
  `item_extras`, `error_map`. Notices: `on_act(session, notice, action, user_id, now)` (may return a mapping merged
  beside `notice`), `act_dep`, `after_act`, `actions`.
- `item_extras(task)` is merged after the 24 item keys and never replaces one: a base key always wins.
- A `TaskError` answers `error_map(exc)` or, by default, its own status with `{"detail": {code, message}}`. A
  `NoticeError` answers the same way. The notices router also answers, by default, any exception raised inside a route (so inside `on_act` too) that
  carries a string `code`, a string `message` and an integer `status` and no `detail` of its own: a `TaskError` from the
  task action is answered with its status and the same body, with no import between the two libs. `error_map` on the
  notices router replaces that rule.

## What stays app-side

The capability checks (`tasks.write`, read-all), the notices a task change puts away, the calendar mirror after the
commit, link labels, the `prepare` rule, the work-day defaults, the clock. The capture, link search, push and sync
routes are not factories.

## Consequences

- `services/sdk_example` mounts both factories (113 lines) in place of 287 lines of its own routes plus 38 lines of
  helpers. Its 427 tests pass; one changed (a spy that patched the deleted module now patches `bond_notify_py.service`).
- The act route does not read a `time_zone` query value: `on_act` has no request, so the example answers the task in the
  person's stored zone. Pass the zone another way if an app needs it.
