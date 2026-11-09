# Changelog

## 0.1.0 - unreleased
- `CalendarProvider` protocol: `list_events`, `create_event`, `update_event` (etag), `delete_event`, `get_event`.
- `MsGraphCalendarProvider` (calendarView paging with a 25-page cap, If-Match writes) and `GoogleCalendarProvider`
  (reads plus new writes; cancelled and self-declined events dropped).
- `CalendarEvent`, `CalendarEventDraft`, `EventPage`, `EventPatch`: aware UTC datetimes, all-day at midnight UTC.
- Typed errors: `CalendarError`, `NotFound`, `EtagMismatch`, `ReconnectRequired`, `Unavailable`.
- `FakeCalendarProvider` with etags and `fail_next`.
