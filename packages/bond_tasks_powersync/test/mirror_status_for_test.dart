import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_powersync/bond_tasks_powersync.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

final now = DateTime.utc(2026, 3, 11, 20);

Map<String, Object?> _row(String id, {Object? status, int mirror = 1}) => {
      ...rowOf(fixture('task_timed.json')),
      'id': id,
      'mirror_enabled': mirror,
      'mirror_status': status,
    };

void main() {
  test('default: the stored mirror_status is shown, as before', () async {
    final repo = repoFor(fakeTasks([_row('a', status: 'mirrored'), _row('b', status: null)]), now: now);
    final by = {for (final t in await repo.watchOpen().first) t.id: t.mirrorStatus};
    expect(by, {'a': MirrorStatus.mirrored, 'b': MirrorStatus.pending});
  });

  test('a hook value wins over the stored value', () async {
    final repo = PowerSyncTaskRepository(
      fakeTasks([_row('a', status: 'pending'), _row('b', status: 'mirrored')]),
      userId: 'user-1',
      clock: TaskClock(() => now),
      mirrorStatusFor: (row) => row['id'] == 'a' ? 'failed' : null,
    );
    final by = {for (final t in await repo.watchOpen().first) t.id: t.mirrorStatus};
    expect(by, {'a': MirrorStatus.failed, 'b': MirrorStatus.mirrored});
  });

  test('a hook returning null keeps the stored value', () async {
    final repo = PowerSyncTaskRepository(
      fakeTasks([_row('a', status: 'skipped')]),
      userId: 'user-1',
      clock: TaskClock(() => now),
      mirrorStatusFor: (row) => null,
    );
    expect((await repo.list(const TaskFilters())).items.single.mirrorStatus, MirrorStatus.skipped);
  });

  test('the hook sees the stored row and also shapes a write result and writes nothing back', () async {
    final db = fakeTasks([_row('a', status: 'pending', mirror: 0)]);
    final seen = <Object?>[];
    final repo = PowerSyncTaskRepository(
      db,
      userId: 'user-1',
      clock: TaskClock(() => now),
      mirrorStatusFor: (row) {
        seen.add(row['mirror_enabled']);
        return (row['mirror_enabled'] == 0) ? 'skipped' : null;
      },
    );
    final t = await repo.update('a', const TaskPatch(title: 'Renamed'));
    expect(t.mirrorStatus, MirrorStatus.skipped);
    expect(seen, contains(0));
    final w = db.statements.firstWhere((s) => s.sql.startsWith('UPDATE'));
    expect(w.sql, isNot(contains('mirror_status')));
  });

  test('taskFromRow takes the same hook', () {
    final row = _row('a', status: 'pending');
    expect(taskFromRow(row, nowUtc: now).mirrorStatus, MirrorStatus.pending);
    expect(taskFromRow(row, nowUtc: now, mirrorStatusFor: (_) => 'mirrored').mirrorStatus, MirrorStatus.mirrored);
  });
}
