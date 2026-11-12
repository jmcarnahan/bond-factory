# Changelog

## 0.1.0 - unreleased
- `CalendarEventDraft.attendees` (and the `attendees` patch key) may hold `str | Person`. A `Person` with a name writes the
  display name to both providers (Graph `emailAddress.name`, Google `displayName`); a plain string behaves as before, so
  the default payload is unchanged. A `Person` with no address raises `InvalidAttendee` (new, exported; a `CalendarError` and a `ValueError`; status 422, code `invalid_attendee`). Duplicate attendees merge by lower-cased address, a named entry winning (`models.merged_attendees`). New helper `attendee_parts`
  (in `bond_calendar.models`, not exported from the barrel). The fake keeps the name on the `Attendee`.
- `Forbidden(CalendarError)`: HTTP 403 from either provider now raises it (status 403, the provider's own code kept in
  `.code`, for example `insufficientPermissions` or `ErrorAccessDenied`). It is a `CalendarError`, so code that caught
  `CalendarError` for a 403 still works.
  A Google 403 whose reason is a throttle (`rateLimitExceeded`, `userRateLimitExceeded`, `quotaExceeded`, `dailyLimitExceeded`,
  `calendarUsageLimitsExceeded`) raises `Unavailable` (status 403, `.code` the reason) so a caller retries.
- `CalendarEventDraft.reminder_off: bool = False`. True on create: Graph gets `isReminderOn: false`, Google gets
  `reminders: {"useDefault": false}` with no overrides, so a new event has no reminder instead of the mailbox default.
  Ignored when `reminder_minutes` is set. It is not an `EventPatch` key (a patch with it raises `ValueError`): to clear a
  reminder later, patch `reminder_minutes` to `None`. The default leaves create payloads unchanged.
- Tests: recorded-shape fixtures (`tests/fixtures/`, hand-written from the public API docs, `example.com` only) replayed
  through `httpx.MockTransport`, and an opt-in live test (`BOND_CALENDAR_NETWORK=1` plus `BOND_CALENDAR_TOKEN`).
- Behaviour change: Graph `update_event` now raises `ValueError` for a patch with `start` or `end` but no
  `is_all_day` (it used to write UTC instants), the same as Google already did.
- All-day drafts on Graph in the app's zone: an all-day draft's date is the UTC date of its start (end: the UTC date of
  its end, at least the day after); with a non-UTC `timezone=` Graph gets local midnight of that date with the zone's
  Windows name, so the mailbox shows it all-day on the right day. Google still writes `{"date": ...}` and takes no zone. Without a zone, or with UTC, behaviour is unchanged. The zone is not validated: Graph gets
  the Windows name when the lib knows one, otherwise the name as given; a non-string zone raises `CalendarError` on an
  all-day write. `tzdata` is a dependency.
- `refresh=` on both providers and `transport.call`: on a 401 it is called once and the request is retried once with
  the new token; a second 401 raises `ReconnectRequired`. No other status is retried.
- `CalendarProvider` protocol: `list_events`, `create_event`, `update_event` (etag), `delete_event`, `get_event`.
- `MsGraphCalendarProvider` (calendarView paging with a 25-page cap, If-Match writes) and `GoogleCalendarProvider`
  (reads plus new writes; cancelled and self-declined events dropped).
- `CalendarEvent`, `CalendarEventDraft`, `EventPage`, `EventPatch`: aware UTC datetimes, all-day at midnight UTC.
- Typed errors: `CalendarError`, `NotFound`, `EtagMismatch`, `ReconnectRequired`, `Unavailable`.
- `FakeCalendarProvider` with etags and `fail_next`.
