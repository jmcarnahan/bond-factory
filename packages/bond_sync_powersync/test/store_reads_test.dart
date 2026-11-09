import 'dart:async';

import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_sync_db.dart';

Future<void> tick() => Future<void>.delayed(Duration.zero);

void main() {
  test('changeTargets names the view and the raw table, local-only and ps_crud', () {
    expect(changeTargets(['notes']), ['notes', 'ps_data__notes']);
    expect(
      changeTargets(['a'], localOnly: ['sync_rejections'], crud: true),
      ['a', 'ps_data__a', 'sync_rejections', 'ps_data_local__sync_rejections', 'ps_crud'],
    );
  });

  test('storeChanges subscribes to those names', () async {
    final db = FakeSyncDb();
    final seen = <void>[];
    final sub = storeChanges(db, ['notes']).listen(seen.add);
    db.changes.add(null);
    await tick();
    await sub.cancel();
    expect(db.changeSubscriptions.single, ['notes', 'ps_data__notes']);
    expect(seen, hasLength(1));
  });

  test('readSnapshot runs in one read transaction', () async {
    final db = FakeSyncDb()..onGetAll = (sql, p) => [{'n': 1}];
    final v = await readSnapshot(db, (sql) async => (await sql.getAll('SELECT 1')).length);
    expect(v, 1);
    expect(db.reads, 1);
  });

  test('watchSnapshot reads now and again after each change', () async {
    final db = FakeSyncDb();
    var n = 0;
    final seen = <int>[];
    final sub = watchSnapshot<int>(db, ['notes'], (sql) async => ++n).listen(seen.add);
    await tick();
    db.changes.add(null);
    await tick();
    db.changes.add(null);
    await tick();
    await sub.cancel();
    expect(seen, [1, 2, 3]);
  });

  test('the latest read wins over a slower earlier one', () async {
    final db = FakeSyncDb();
    final slow = Completer<int>();
    var call = 0;
    final seen = <int>[];
    final sub = watchSnapshot<int>(db, ['notes'], (sql) {
      call += 1;
      return call == 1 ? slow.future : Future.value(2);
    }).listen(seen.add);
    await tick();
    db.changes.add(null); // second read finishes first
    await tick();
    slow.complete(1);
    await tick();
    await sub.cancel();
    expect(seen, [2]);
  });

  test('errors reach the stream and cancelling stops reads', () async {
    final db = FakeSyncDb();
    final errors = <Object>[];
    final sub = watchSnapshot<int>(db, ['notes'], (sql) async => throw StateError('bad')).listen((_) {}, onError: errors.add);
    await tick();
    expect(errors.single, isA<StateError>());
    await sub.cancel();
    final before = db.reads;
    db.changes.add(null);
    await tick();
    expect(db.reads, before);
  });
}
