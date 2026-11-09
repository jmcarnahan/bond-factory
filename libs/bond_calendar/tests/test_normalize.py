from datetime import UTC, datetime

from bond_calendar.normalize import google_event, graph_event
from bond_calendar.times import parse_instant, round_to_midnight


def utc(*parts):
    return datetime(*parts, tzinfo=UTC)


def test_graph_full_event():
    raw = {
        "id": "a", "@odata.etag": 'W/"1"', "subject": "Sync", "isOrganizer": True, "showAs": "busy",
        "start": {"dateTime": "2026-07-02T10:00:00.0000000", "timeZone": "UTC"},
        "end": {"dateTime": "2026-07-02T10:30:00.0000000", "timeZone": "UTC"},
        "location": {"displayName": "Room 1"}, "organizer": {"emailAddress": {"name": "Ann", "address": "ann@example.com"}},
        "attendees": [{"emailAddress": {"name": "Bo", "address": "bo@example.com"}, "type": "required",
                       "status": {"response": "accepted"}}],
        "isOnlineMeeting": True, "onlineMeeting": {"joinUrl": "https://meet.example.com/x"},
        "seriesMasterId": "m", "type": "occurrence", "bodyPreview": "hello", "webLink": "https://w.example.com",
        "responseStatus": {"response": "organizer"}, "sensitivity": "normal", "categories": ["Blue"],
    }
    e = graph_event(raw)
    assert (e.id, e.etag, e.subject, e.start, e.end) == ("a", 'W/"1"', "Sync", utc(2026, 7, 2, 10), utc(2026, 7, 2, 10, 30))
    assert e.location == "Room 1" and e.organizer.email == "ann@example.com"
    assert e.attendees[0].email == "bo@example.com" and e.attendees[0].response == "accepted"
    assert e.is_organizer and e.is_online_meeting and e.join_url == "https://meet.example.com/x"
    assert (e.series_master_id, e.event_type, e.preview, e.response_status) == ("m", "occurrence", "hello", "organizer")
    assert e.categories == ["Blue"] and e.body is None


def test_graph_missing_fields_do_not_raise():
    e = graph_event({})
    assert e.id == "" and e.start is None and e.attendees == [] and e.categories == [] and not e.is_cancelled


def test_graph_all_day_rounds_to_nearest_midnight():
    raw = {"id": "d", "isAllDay": True, "start": {"dateTime": "2026-07-24T17:00:00.0000000", "timeZone": "UTC"},
           "end": {"dateTime": "2026-07-25T17:00:00.0000000", "timeZone": "UTC"}}
    e = graph_event(raw)
    assert e.is_all_day and e.start == utc(2026, 7, 25) and e.end == utc(2026, 7, 26)


def test_graph_all_day_midnight_is_unchanged():
    raw = {"isAllDay": True, "start": {"dateTime": "2026-07-25T00:00:00.0000000", "timeZone": "UTC"},
           "end": {"dateTime": "2026-07-26T00:00:00.0000000", "timeZone": "UTC"}}
    assert graph_event(raw).start == utc(2026, 7, 25)


def test_graph_named_zone_is_converted_to_utc():
    raw = {"start": {"dateTime": "2026-07-25T15:00:00.0000000", "timeZone": "Pacific Standard Time"},
           "end": {"dateTime": "2026-07-25T16:00:00.0000000", "timeZone": "America/Los_Angeles"}}
    e = graph_event(raw)
    assert e.start == utc(2026, 7, 25, 22) and e.end == utc(2026, 7, 25, 23)


def test_unknown_zone_reads_as_utc():
    assert parse_instant("2026-07-25T15:00:00", "Nowhere Standard Time") == utc(2026, 7, 25, 15)


def test_offset_time_converts_to_utc():
    assert parse_instant("2026-07-02T10:00:00+02:00") == utc(2026, 7, 2, 8)
    assert parse_instant("2026-07-02T10:00:00Z") == utc(2026, 7, 2, 10)
    assert parse_instant("2026-07-02T10:00:00.1234567+00:00") == utc(2026, 7, 2, 10).replace(microsecond=123456)


def test_unreadable_instants_are_none():
    assert parse_instant("not a date") is None and parse_instant(None) is None and parse_instant("") is None


def test_round_to_midnight_edges():
    assert round_to_midnight(utc(2026, 7, 2, 11, 59)) == utc(2026, 7, 2)
    assert round_to_midnight(utc(2026, 7, 2, 12)) == utc(2026, 7, 3)
    assert round_to_midnight(None) is None


def test_google_timed_event_in_offset_becomes_utc():
    raw = {"id": "g", "etag": '"e"', "summary": "Lunch", "start": {"dateTime": "2026-07-02T12:00:00-07:00"},
           "end": {"dateTime": "2026-07-02T13:00:00-07:00"}, "location": "Cafe", "htmlLink": "https://g.example.com",
           "organizer": {"email": "me@example.com", "self": True}, "visibility": "private", "transparency": "transparent",
           "hangoutLink": "https://meet.example.com/g", "description": "d" * 400, "recurringEventId": "r",
           "attendees": [{"email": "me@example.com", "self": True, "responseStatus": "tentative"},
                         {"email": "x@example.com", "displayName": "X", "optional": True, "responseStatus": "needsAction"}]}
    e = google_event(raw)
    assert (e.start, e.end) == (utc(2026, 7, 2, 19), utc(2026, 7, 2, 20))
    assert e.is_organizer and e.show_as == "free" and e.sensitivity == "private" and e.join_url and e.is_online_meeting
    assert e.response_status == "tentativelyAccepted" and e.attendees[1].type == "optional"
    assert e.attendees[1].response == "notResponded" and len(e.preview) == 255
    assert (e.series_master_id, e.event_type, e.web_link) == ("r", "occurrence", "https://g.example.com")


def test_google_all_day_is_midnight_utc():
    e = google_event({"id": "d", "start": {"date": "2026-07-02"}, "end": {"date": "2026-07-03"}})
    assert e.is_all_day and e.start == utc(2026, 7, 2) and e.end == utc(2026, 7, 3)
    assert e.show_as == "busy" and e.sensitivity == "normal" and e.event_type == "singleInstance"


def test_google_missing_fields_do_not_raise():
    e = google_event({"attendees": ["junk", None]})
    assert e.id == "" and e.start is None and e.attendees == [] and e.organizer is None
