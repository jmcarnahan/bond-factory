import 'package:bond_sync_powersync/testing.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('table mode answers SELECT from the named table', () async {
    final db = FakeSyncDb.tables({
      'tasks': [
        {'id': 'a'},
        {'id': 'b'},
      ],
    });
    expect((await db.getAll('SELECT * FROM tasks')).length, 2);
    expect((await db.getOptional('SELECT * FROM tasks'))?['id'], 'a');
    expect(await db.getAll('SELECT * FROM other'), isEmpty);
    db.refineRows = (sql, p, rows) => [for (final r in rows) if (r['id'] == p.first) r];
    expect((await db.getAll('SELECT * FROM tasks WHERE id = ?', ['b'])).single['id'], 'b');
  });

  test('watch controllers are per SQL, the old one reaches all, snapshot on listen', () async {
    final db = FakeSyncDb.tables({
      'tasks': [
        {'id': 'a'},
      ],
    }, emitOnListen: true);
    final one = <int>[];
    final two = <int>[];
    final s1 = db.watch('SELECT * FROM tasks').listen((r) => one.add(r.length));
    final s2 = db.watch('SELECT id FROM tasks').listen((r) => two.add(r.length));
    await pumpEventQueue();
    expect(one, [1]);
    expect(two, [1]);
    db.watchControllerFor('SELECT * FROM tasks').add([]);
    db.watchController.add([{}, {}]);
    await pumpEventQueue();
    expect(one, [1, 0, 2]);
    expect(two, [1, 2]);
    await s1.cancel();
    await s2.cancel();
  });
}
