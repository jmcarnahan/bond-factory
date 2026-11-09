// Run by time_zone_test.dart in a child process with a TZ environment value.
// Prints one line per case so the parent can compare them.
import 'dart:io';

import 'package:bond_json/bond_json.dart';

void main() {
  for (final s in [
    '2026-01-02T03:04:05',
    '2026-07-02T03:04:05.123',
    '2026-07-02 03:04:05',
    '2026-03-08T02:30:00', // a local time that does not exist in New York
    '2026-11-01T01:30:00', // a local time that happens twice in New York
    '2026-07-02',
    '2026-07-02T03:04:05Z',
    '2026-07-02T05:04:05+02:00',
  ]) {
    final t = jtime({'t': s}, 't')!;
    stdout.writeln('${t.isUtc} ${jiso(t)}');
  }
}
