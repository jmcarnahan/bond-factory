# 2026-11-11 Daily TODO checklist: scope and modules

Status: accepted. Dated, append-only. Amends D1 and D2 of `2026-11-08-sdk-architecture.md`.

## Requirement

Every app that uses the shared modules can offer a daily checklist of TODO tasks. A TODO has no start time, an
optional due time (with none it is due at the user's end of day), an optional priority, and links to one or
more contacts. It is created by hand or from a phrase through a model call. It appears on the calendar and the
home page. The user is notified when the due time is close, when it arrives, and each morning after, for a
limited number of days, until it is done or cancelled.

## Decisions

- **T1 Scope (amends D1).** The SDK now also ships: a capture library with a model-client Protocol and no
  vendor client; a `Notifier` seam; a stored inbox; local phone notifications; an Apple push transport. Vendor
  model clients, a contacts module, a shared calendar UI and an events module stay out. Phones are iOS only.
- **T2 Tasks (amends D2).** Reminders are three stages (close, due, past) decided by a sweep that any
  scheduler may call. The sweep does not need the job queue. The single queued reminder is retired.
- **T3 One build.** No staged releases. Everything is additive until the final integration step, which
  removes the queued reminder together with its callers.
- **T4 Headless first.** Dart models, clients, a repository interface and a framework-free controller are the
  deliverable. `Bond*` widgets are the reference.
- **T5 Each app keeps its contacts and calendar screens.** Tasks plug in through resolver Protocols and small
  widgets (due lane, month marker, today list).
- **T6 Capture.** One model call returns items; each is a task ("must be done by a time") or an event
  ("happens at a time"). The route creates nothing; the user reviews. No classifier step in this build.
  Contact ids are never sent to the model. The text is never logged. Spend limits belong to the app.
- **T7 Recurrence is not built.** A future recurring TODO is modelled as generated rows, one per occurrence;
  the ledger key stays on the task id; no series column is added now.
- **T8 One word.** A task whose due instant has passed is "overdue". There is no second flag. An event in the
  past is "missed", never "overdue".

## Module list (added to the list in the architecture record)

Python libs: `bond_notify_py`, `bond_push_py`, `bond_capture_py`.
Dart core: `bond_notify`. Flutter: `bond_notify_ui`, `bond_push`, `bond_tasks_notifications`,
`bond_tasks_powersync`, `bond_notify_powersync`.

## Consequences

- A library still imports no other library. The sweep hands notifiers a session and a notice object; inbox and
  push notifiers satisfy the Protocols by shape, and the app wires them.
- Every new table is a mixin; the app's migration creates it.
- Real Apple push delivery cannot be tested in this repo; tests use fakes.
