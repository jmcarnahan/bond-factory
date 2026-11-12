# bond_calendar

Calendar provider clients for Microsoft Graph and Google Calendar behind one `CalendarProvider` protocol.
Depends on `httpx` only and stores nothing. A provider takes a `token: Callable[[], str]` (for example a closure over
the OAuth lib's access-token call) and an `httpx.Client`.

```python
import httpx
from bond_calendar import CalendarEventDraft, MsGraphCalendarProvider

provider = MsGraphCalendarProvider(lambda: access_token(), httpx.Client(timeout=15))
page = provider.list_events(start=start_utc, end=end_utc)   # EventPage(events, truncated)
made = provider.create_event(CalendarEventDraft("Call", start_utc, end_utc))
provider.update_event(made.id, {"subject": "Call (moved)"}, etag=made.etag)  # EtagMismatch on a stale etag
```

- Every instant is an aware UTC `datetime`; all-day events sit at midnight UTC.
- Graph `update_event` raises `ValueError` for a `start`/`end` patch without `is_all_day` (as Google does).
- All-day drafts carry a calendar date at midnight UTC; the Graph provider's `timezone` (IANA or Windows name)
  only decides how Graph writes it: local midnight of that date, with the zone's Windows name.
- `GoogleCalendarProvider(token, http, *, refresh=...)` takes no zone: it always sends the all-day date itself.
- `refresh=lambda: new_token()`: on a 401 the provider calls it once and retries once; a second 401 raises.
  A refresh that raises becomes `ReconnectRequired` (the original is `__cause__`).
- Errors: `NotFound`, `EtagMismatch` (412), `ReconnectRequired` (401), `Forbidden` (403, provider code in `.code`; a throttle 403 is `Unavailable`),
  `Unavailable` (5xx, 429, timeout).
- Draft `attendees` are e-mail strings or `Person(name, email)`: the name is written as the display name on both providers. Duplicates merge by lower-cased address (a named entry wins); a `Person` with no address raises `InvalidAttendee` (422).
- `CalendarEventDraft(..., reminder_off=True)` creates an event with no reminder (Graph `isReminderOn: false`, Google
  `useDefault: false`, no overrides). `reminder_minutes` wins if both are set. On update, patch `reminder_minutes` to `None`.
- `FakeCalendarProvider` is an in-memory stand-in with etags and `fail_next(exc)` for tests and demos.
- Google writes need the `calendar.events` scope. Google has no categories, so they are ignored there.
- Contract notes and the migration plan: `docs/migration/bond_calendar.md`.
