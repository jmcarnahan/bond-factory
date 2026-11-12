# Migrating to bond_calendar

`libs/bond_calendar` is the calendar half of the two apps that read a calendar today: sbel-crm (app S) over Microsoft
Graph and avalon-crm (app A) over Google. paga-time (app P) has no calendar and adopts nothing. The lib depends on
`httpx` only, stores nothing (the calendar stays the source of truth) and never imports `bond_oauth`: a provider takes
`token: Callable[[], str]` and an `httpx.Client`. The working example is `services/sdk_example`
(`calendar_wiring.py`, `routes/calendar.py`).

## 0. What changed

- Behaviour change to check first: Graph `update_event` now raises `ValueError` for a patch with `start` or `end` but no
  `is_all_day` (it used to write UTC instants); add `is_all_day` to such patches, as Google already required.
- All-day drafts: the date is the UTC date of `start` (the end: the UTC date of `end`, at least the day after), and
  `MsGraphCalendarProvider(timezone=)` writes it as local midnight of that date in that zone, so the mailbox shows
  the right day; Google is unchanged and takes no zone.
  Create then read returns the same date. No zone, no change.
- `refresh: Callable[[], str] | None` on both providers: one forced refresh and one retry on a 401.

## 1. What it replaces

| App | Today | Becomes |
|---|---|---|
| S | `services/msgraph/calendar.py` `list_calendar_view` | `MsGraphCalendarProvider.list_events` (same `$select`, `$orderby`, `$top=100`, `nextLink`, 25-page cap) |
| S | `create_event`, `update_event` (If-Match), `delete_event`, `get_event` | same four methods; `update_event(id, patch, etag=)`, 412 raises `EtagMismatch` |
| S | `_normalize_event` (snake_case dicts, UTC `Z` strings) | `CalendarEvent` dataclass with aware UTC `datetime`s; all-day rounded to the nearest midnight |
| S | `msgraph/client.py` `graph_request` + `GraphError`, `faults.py` | `transport.call` + `CalendarError`, `NotFound`, `EtagMismatch`, `ReconnectRequired` (401), `Unavailable` (5xx, 429, timeout) |
| A | `services/gcal.py` `day_items` (read-only, one day, 60 s cache) | `GoogleCalendarProvider.list_events`; the day window, the 60 s cache and the Today-screen item shape stay in app A |

## 2. What stays in the app

- App S: the CRM category stamped on created events, the deep-link line parsed back out of `bodyPreview`
  (`crm_conversation_id`, `crm_contact_id`, `crm_loan_id`), the body builders (`build_event_body`, the deadline body
  that writes in the officer's wall clock), branding strings, and the router. Build a draft with
  `CalendarEventDraft(..., categories=[crm_category], body=...)`; parse links from `event.preview` and
  `event.categories` in the app. `CalendarEvent.preview` is the raw Graph preview.
- App A: the "needs scope / needs reconnect / unavailable" status dict. Map `ReconnectRequired` to needs reconnect,
  `Unavailable` to unavailable, and a 403 `CalendarError` with `code == "insufficientPermissions"` to needs scope.
- Time zones: the lib is UTC end-to-end except all-day drafts (section 0). A prose-derived "remind me Friday at 3" is converted to UTC by the app
  before it builds the draft; the lib never interprets local wall-clock time. `MsGraphCalendarProvider(timezone=)`
  only chooses the `Prefer: outlook.timezone` header; responses are converted to UTC either way.

## 3. The token seam

`provider_for_connection` in the example is the whole seam. For a real connection the provider gets
`token=lambda: bond_oauth.access_token(session, connection, provider=..., cipher=...)`, wrapped so that
`bond_oauth.ReconnectRequired` becomes `bond_calendar.ReconnectRequired` and `RetryableError` becomes `Unavailable`.
`access_token` marks the connection `needs_reconnect` itself on a rejected refresh; a 401 from the calendar API also
raises `ReconnectRequired`, so the caller should mark the row (`last_error`) too. The provider borrows the session:
use it inside the block that loaded the connection. Read-only paths may pass `mark=False`.

## 4. Call-site changes

- Names: `start/end/is_all_day/...` are unchanged; `crm_*` keys are gone; people are `Person` and `Attendee`
  dataclasses; `attendees` in a draft are e-mail addresses.
- Reads drop cancelled events unless `include_cancelled=True`. Google also drops events the signed-in person declined.
- `delete_event` is idempotent: 204, 404 and 410 all succeed.
- A patch holds only the changed draft keys. When moving a Google all-day event, include `is_all_day` with the new
  dates. Google has no categories, so `categories` is ignored there.
- `FakeCalendarProvider` replaces the `graph_request` patches in S tests: `fail_next(ReconnectRequired())` injects a
  failure, `events` is the assertion list, the etag is `W/"n"` and rises on each change.

## 5. Data and consent

- No tables. `bond_tasks_py` is the only module that stores an external id and etag (for the task mirror).
- App A writes are new code and need the `calendar.events` scope. Today's grant is `calendar.events.readonly`, so every
  app A person reconnects once: `scope_drift(row.scopes, wanted)` from `bond_oauth` reports it; show "Reconnect".
- App S already holds `Calendars.ReadWrite`; no re-consent.

## 6. Acceptance

1. `make -C libs/bond_calendar test` and `lint` pass (offline, `httpx.MockTransport` only).
2. The app's calendar tests pass with `FakeCalendarProvider` in place of the patched Graph client.
3. A real Graph window of one month returns the same events as the old `list_calendar_view`, with the same
   `truncated` answer for a 500-event cap.
4. A write, then an edit in the provider's own app, then a write with the old etag fails with `EtagMismatch`.
5. A revoked connection raises `ReconnectRequired`; the app shows its reconnect banner.
6. `bash tool/boundary_gate.sh` and `bash tool/public_hygiene.sh --worktree` print nothing for `libs/bond_calendar`.

## 7. Known gaps

- `reminder_off` is create-only. To switch a reminder off on an existing event, patch `reminder_minutes` to `None`
  (Graph `isReminderOn: false`; Google `useDefault: false` with empty overrides).
- A 403 now raises `Forbidden` (a `CalendarError` subclass). Catch it for "missing scope or read-only calendar";
  `.code` is the provider's reason.
  Google throttle 403s (`rateLimitExceeded`, `userRateLimitExceeded`, `quotaExceeded`, `dailyLimitExceeded`,
  `calendarUsageLimitsExceeded`) raise `Unavailable` (retry), not `Forbidden`; before this change they were a plain `CalendarError`.
- Recorded-shape fixtures and an opt-in live test now exist (`libs/bond_calendar/tests/`). Run the live one with
  `BOND_CALENDAR_NETWORK=1 BOND_CALENDAR_TOKEN=<short-lived token for a test calendar>` (and
  `BOND_CALENDAR_PROVIDER=google` for Google). It covers acceptance step 4 (write, edit, stale etag, delete).
- Both real providers have run only against `httpx.MockTransport`. `MsGraphCalendarProvider` is lifted from app S's
  working client; `GoogleCalendarProvider` reads are lifted from app A, but its writes (`create_event`, `update_event`,
  `delete_event`) are new code never sent to Google. Acceptance steps 3 and 4 above are the first live run; do them in a
  test calendar first.
