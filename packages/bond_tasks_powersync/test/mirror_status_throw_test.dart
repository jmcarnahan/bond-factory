import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_powersync/bond_tasks_powersync.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

final now = DateTime.utc(2026, 3, 11, 20);

Map<String, Object?> _row(String id, String status) => {
      ...rowOf(fixture('task_timed.json')),
      'id': id,
      'mirror_enabled': 1,
      'mirror_status': status,
    };

void main() {
  test('a hook that throws keeps the stored value for that row; the list still shows', () async {
    final repo = PowerSyncTaskRepository(
      fakeTasks([_row('a', 'mirrored'), _row('b', 'failed')]),
      userId: 'user-1',
      clock: TaskClock(() => now),
      mirrorStatusFor: (row) => row['id'] == 'a' ? throw StateError('boom') : 'skipped',
    );
    final by = {for (final t in await repo.watchOpen().first) t.id: t.mirrorStatus};
    expect(by, {'a': MirrorStatus.mirrored, 'b': MirrorStatus.skipped});
  });

  test('an unknown string from the hook shows as pending', () async {
    final repo = PowerSyncTaskRepository(
      fakeTasks([_row('a', 'mirrored')]),
      userId: 'user-1',
      clock: TaskClock(() => now),
      mirrorStatusFor: (row) => 'no-such-state',
    );
    expect((await repo.watchOpen().first).single.mirrorStatus, MirrorStatus.pending);
  });
}
