// A naive timestamp must read as UTC whatever zone the machine is in. Under
// TZ=UTC (CI) a wrong reading is invisible, so the check runs the parser in
// child processes with other zones.
import 'dart:io';

import 'package:test/test.dart';

const _expected = [
  'true 2026-01-02T03:04:05.000Z',
  'true 2026-07-02T03:04:05.123Z',
  'true 2026-07-02T03:04:05.000Z',
  'true 2026-03-08T02:30:00.000Z',
  'true 2026-11-01T01:30:00.000Z',
  'true 2026-07-02T00:00:00.000Z',
  'true 2026-07-02T03:04:05.000Z',
  'true 2026-07-02T03:04:05.000Z',
];

void main() {
  for (final zone in ['UTC', 'America/New_York', 'Pacific/Auckland', 'Asia/Kolkata']) {
    test('naive, zoned and date-only timestamps read as UTC under TZ=$zone', () async {
      final r = await Process.run(
        Platform.resolvedExecutable,
        ['run', 'test/tz_probe.dart'],
        environment: {'TZ': zone},
        workingDirectory: Directory.current.path,
      );
      expect(r.exitCode, 0, reason: '${r.stderr}');
      expect((r.stdout as String).trim().split('\n').map((l) => l.trim()).toList(), _expected);
    }, timeout: const Timeout(Duration(seconds: 60)));
  }
}
