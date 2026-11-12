# Changelog

## 0.1.0 - unreleased
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
