# Changelog

## 0.1.0 - unreleased
- Scaffold.
- Readers `jstr`, `jint`, `jnum`, `jbool`, `jmap`, `jlist`, `jlistOf`: missing or null keys read as null (or an empty list), a wrong type throws `JsonShapeError(path, expected, actual)`.
- `jint` accepts int, any num (truncated) and numeric strings; `jnum` accepts num and numeric strings; `jbool` takes bools only.
- `jtime` reads ISO-8601 strings only (ints throw). `Z`, offsets and naive strings all come back UTC; a naive string counts as UTC; a date-only string is midnight UTC; an empty string is null.
- `jtimeOrNull` reads like `jtime` but never throws: a missing, null, empty, non-String or malformed value is null.
- Fix: `jtime` and `jtimeOrNull` reject impossible calendar dates and times instead of rolling them over to the next valid one. `jtime` throws `JsonShapeError`; a leap day (2028-02-29) still reads. Rejected now: a month outside 1-12, a day past the month's end (leap years respected), an hour above 23 (so `24:00` is out), a minute above 59 and a second above 59 (so the leap second `23:59:60` is out; it used to read as the next minute). The check covers the extended form (`2026-02-30T10:00Z`), the basic form (`20260230T101010Z`) and an hour-only time (`2026-11-08T25`). A year with a sign or more than four digits (`-2026-...`, `10000-...`) is not checked. Every valid input reads the same UTC instant as before.
- `jiso` writes UTC with millisecond precision and a trailing `Z`.
- `enumByWire` returns null for a null or unknown wire string.
- Decision: the seed's tolerant defaults (wrong type reads as a fallback) are not kept; a wrong type throws so a contract break is loud.
