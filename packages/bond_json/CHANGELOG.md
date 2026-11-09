# Changelog

## 0.1.0 - unreleased
- Scaffold.
- Readers `jstr`, `jint`, `jnum`, `jbool`, `jmap`, `jlist`, `jlistOf`: missing or null keys read as null (or an empty list), a wrong type throws `JsonShapeError(path, expected, actual)`.
- `jint` accepts int, any num (truncated) and numeric strings; `jnum` accepts num and numeric strings; `jbool` takes bools only.
- `jtime` reads ISO-8601 strings only (ints throw). `Z`, offsets and naive strings all come back UTC; a naive string counts as UTC; a date-only string is midnight UTC; an empty string is null.
- `jiso` writes UTC with millisecond precision and a trailing `Z`.
- `enumByWire` returns null for a null or unknown wire string.
- Decision: the seed's tolerant defaults (wrong type reads as a fallback) are not kept; a wrong type throws so a contract break is loud.
