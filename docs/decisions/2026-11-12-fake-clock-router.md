# 2026-11-12 One fake-clock router in bond_service_kit

Status: accepted. Dated, append-only.

## Context

A walk needs to pin the server clock so a day boundary or a notice stage can be reached without waiting. The example
service had its own hand-written `GET` and `PUT /fake/clock`. An adopting app would have copied it, and each copy
decides for itself how to stay closed in production.

## Decisions

- **F1** `bond_service_kit.fake_clock_router(clock, *, enabled, dependencies=())` builds the router. The app mounts it
  where it wants it. The library reads no environment: `enabled()` is called on every request, and when it is false
  every request answers 404 `not_found`, before the body is read and before any extra dependency (such as auth) runs.
- **F2** Wire, both verbs: `{"now": "2026-11-08T10:30:00Z" | null}`. `PUT` pins the clock to the instant (an offset is
  converted to UTC, no offset is read as UTC); `null` or an absent `now` releases it. A bad value is 422 `invalid_now`.
  The body refuses unknown keys.
- **F3** The clock is a Protocol (`PinnableClock`: `frozen`, `now()`, `freeze(at)`, `unfreeze()`). `bond_service_kit.Clock`
  satisfies it as it is.

## Consequences

- An adopting app mounts the router behind its own flag and an auth dependency. Nothing else in a build can reach it.
- The example keeps a small adapter (`clock_pin.py`) so that "pinned through the route" stays separate from "frozen by
  a test fixture or by `/jobs/tick`"; `/jobs/tick` goes back to the pin, or releases the clock when there is none.
- The sync upload and the sync token report the app clock, so a phone's server clock follows the pin.
