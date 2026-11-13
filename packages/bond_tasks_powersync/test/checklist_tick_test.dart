import 'dart:convert';

import 'package:bond_sync_powersync/testing.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

Stmt lastUpdate(FakeSyncDb db) => db.statements.lastWhere((s) => s.sql.startsWith('UPDATE'));

List<Map<String, Object?>> cellOf(FakeSyncDb db) =>
    (jsonDecode(db.tables['tasks']!.single['checklist']! as String) as List).cast<Map<String, Object?>>();

/// Pinned operation: ticking and unticking a checklist item through `update`. A ticked item is stored and queued with its
/// `done_at` and no `done`; an item unticked with `copyWith(clearDone: true)` carries `done: false` (the server unticks it); an
/// item never ticked carries no `done`, so a stale phone copy never unticks another person's tick.
void main() {
  test('tick, untick, and the stale-copy guarantee', () async {
    final db = fakeTasks([rowOf(fixture('task_timed.json'))]);
    final repo = repoFor(db, now: DateTime.utc(2026, 3, 11, 20));
    final id = db.tables['tasks']!.single['id']! as String;
    final tick = DateTime.utc(2026, 3, 11, 19);
    final one = ChecklistItem(id: 'c1', text: 'one', doneAt: tick);
    const two = ChecklistItem(id: 'c2', text: 'two');

    await repo.update(id, TaskPatch(checklist: [one, two]));
    var cell = cellOf(db);
    expect(cell[0].containsKey('done'), isFalse);
    expect(cell[0]['done_at'], '2026-03-11T19:00:00.000Z');
    expect(cell[1].containsKey('done'), isFalse, reason: 'never ticked: no done key');
    expect(cell[1]['done_at'], isNull);
    expect(lastUpdate(db).params.first, isNot(contains('"done"')));

    await repo.update(id, TaskPatch(checklist: [one.copyWith(clearDone: true), two]));
    cell = cellOf(db);
    expect((cell[0]['done'], cell[0]['done_at']), (false, null));
    expect(cell[1].containsKey('done'), isFalse);
    expect(lastUpdate(db).params.first, contains('"done":false'));

    // a second edit that re-reads the row and adds an item re-sends the earlier items WITHOUT done
    final reread = (await repo.getTask(id))!;
    await repo.update(id, TaskPatch(checklist: [...reread.checklist, const ChecklistItem(id: 'c3', text: 'three')]));
    cell = cellOf(db);
    expect(cell, hasLength(3));
    expect(cell.any((c) => c.containsKey('done')), isFalse);
    expect(lastUpdate(db).params.first, isNot(contains('"done"')));
  });
}
