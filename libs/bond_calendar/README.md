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
- Errors: `NotFound`, `EtagMismatch` (412), `ReconnectRequired` (401), `Unavailable` (5xx, 429, timeout).
- `FakeCalendarProvider` is an in-memory stand-in with etags and `fail_next(exc)` for tests and demos.
- Google writes need the `calendar.events` scope. Google has no categories, so they are ignored there.
- Contract notes and the migration plan: `docs/migration/bond_calendar.md`.
