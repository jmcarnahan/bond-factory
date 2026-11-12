# 2026-11-11 The due instant, time zones and the work day

Status: accepted. Dated, append-only.

## Context

A task had a calendar `due_date` and a wall-clock `due_time`, and one zone per app. Users in different zones,
a per-user end of day and notifications by instant need one stored moment.

## Rules

1. `due_at` is server-authoritative, naive UTC, truncated to the minute, and null if and only if `due_date` is
   null. A dated task whose `due_at` is null is "not yet computed"; the sweep repairs it.
2. `overdue` means: open and `due_at < now`. The summary count and the list sections use the same test.
3. Timed task (`due_time` set): `due_at` is that wall-clock time in a zone, converted to UTC. The zone is the
   one sent with the write, else the writer's stored zone, else the app default. A client-sent `due_at` is
   accepted only when its offset from the wall clock is a multiple of 15 minutes within -12:00 to +14:00 and
   agrees with a zone name sent beside it (the name wins). Otherwise it is ignored and recomputed. A write is
   never rejected because of `due_at`.
4. Date-only task: `due_at` is `due_date` at the end of day of the responsible user (the assignee, else the
   owner), in that user's stored zone; if none is stored and the writer is that user, the zone sent with the
   write; else the app default. A client `due_at` is ignored. A task write never stores a zone.
5. `due_at` is recomputed only when a write changes `due_date`, `due_time` or `assigned_user_id` (the new
   value differs from the stored one; resending an unchanged value from another zone moves nothing), or
   when the responsible user's end of day or zone changes. A timed task is never recomputed by settings.
6. A replayed create is a no-op. A replayed patch applies the rules against the current settings.
7. Daylight saving: a local time that does not exist moves forward; an ambiguous one takes the first
   occurrence. A lead is subtracted from the instant, not from the wall clock.
8. A task's day for a viewer is `due_date` when date-only, else the viewer-zone date of `due_at`. Open tasks
   fall in exactly one section: overdue, today, upcoming, undated.
9. A device sends `due_at` only for a timed task, computed in its own current zone, and nothing for a
   date-only task. Pure-Dart packages carry no time-zone database; the app passes the IANA zone name.

## Per-user settings

A table keyed by user id, no foreign key; no row means defaults. `time_zone` (reported by the client when it
changes), `start_of_day` (08:00), `end_of_day` (17:00), `lead_minutes` (60). Quiet hours are not stored: they
are the time after `end_of_day` and before `start_of_day`. The instant of `end_of_day` is not quiet.

## Reminder setting

`remind_minutes_before`: `-3` use my default (the default for new tasks), `-2` no "close" notice, `-1` the
morning of the due date, `N >= 0` minutes before, at most 10080. "Due" and "past" notices do not depend on it.

## Consequences

- `overdue` changes meaning on the wire (it was "due date before the client's today"). Clients pinned to an
  older commit keep working but show the date-based sections until they update.
- New columns `priority` and `due_at` are additive. `remind_at` and `reminded_at` are removed.
- Wire datetimes are ISO 8601 with `Z`. A naive string is UTC by convention; a device never writes local time.
