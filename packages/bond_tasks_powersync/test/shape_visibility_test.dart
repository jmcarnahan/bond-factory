import 'package:flutter_test/flutter_test.dart';

import 'shape_support.dart';

const order = 'ORDER BY due_date IS NULL, due_date, due_time IS NULL, due_time, created_at DESC, id';
const mineSql = '(owner_user_id = ? OR assigned_user_id = ?)';

void main() {
  final rows = [
    legacyRow('a', {'client_ref': 'C1'}),
    legacyRow('b', {'client_ref': 'C1', 'owner_user_id': 'other'}),
    legacyRow('c', {'client_ref': 'C2', 'owner_user_id': 'other', 'assigned_user_id': 'user-1'}),
    legacyRow('d', {'client_ref': 'C2', 'owner_user_id': 'other'}),
    legacyRow('e', {'client_ref': 'C1', 'status': 'cancelled'}),
    legacyRow('f', {'status': 'done', 'completed_at': '2026-03-10T00:00:00.000Z'}),
  ];

  test('everyone: an empty map lists all rows; exact SQL', () async {
    final db = legacyDb(rows);
    final page = await legacyRepo(db).listWhere({});
    expect(page.items.map((t) => t.id).toSet(), {'a', 'b', 'c', 'd', 'e', 'f'});
    expect(page.total, 6);
    expect(db.statements.map((s) => s.toString()), [
      'tx SELECT * FROM tasks $order LIMIT ? OFFSET ? [25, 0]',
      'tx SELECT COUNT(*) AS n FROM tasks []',
    ]);
  });

  test('mine: owner or assignee, nothing else; SQL and params', () async {
    final db = legacyDb(rows);
    final page = await legacyRepo(db).listWhere({}, mine: true);
    expect(page.items.map((t) => t.id).toSet(), {'a', 'c', 'e', 'f'});
    expect(page.total, 4);
    expect(db.statements.first.toString(), 'tx SELECT * FROM tasks WHERE $mineSql $order LIMIT ? OFFSET ? [user-1, user-1, 25, 0]');
    expect(db.statements.last.toString(), 'tx SELECT COUNT(*) AS n FROM tasks WHERE $mineSql [user-1, user-1]');
  });

  test('a linked record, mine or not; the mine condition sits after the equals and before the status', () async {
    final db = legacyDb(rows);
    final repo = legacyRepo(db);
    expect((await repo.listWhere({'client_ref': 'C1'}, status: 'open')).items.map((t) => t.id).toSet(), {'a', 'b'});
    db.statements.clear();
    final mine = await repo.listWhere({'client_ref': 'C1'}, mine: true, status: 'open');
    expect(mine.items.map((t) => t.id), ['a']);
    expect(db.statements.first.toString(), 'tx SELECT * FROM tasks WHERE client_ref = ? AND $mineSql AND status = ? $order LIMIT ? OFFSET ? [C1, user-1, user-1, open, 25, 0]');
    expect(db.statements.last.toString(), 'tx SELECT COUNT(*) AS n FROM tasks WHERE client_ref = ? AND $mineSql AND status = ? [C1, user-1, user-1, open]');
    db.statements.clear();
    await repo.listWhere({}, status: 'open');
    expect(db.statements.first.toString(), "tx SELECT * FROM tasks WHERE status = ? $order LIMIT ? OFFSET ? [open, 25, 0]");
  });

  test('cancelled rows appear only when the status is not open or done', () async {
    final repo = legacyRepo(legacyDb(rows));
    for (final s in ['open', 'done']) {
      expect((await repo.listWhere({'client_ref': 'C1'}, status: s)).items.map((t) => t.id), isNot(contains('e')), reason: s);
    }
    expect((await repo.listWhere({'client_ref': 'C1'}, status: 'cancelled')).items.map((t) => t.id), ['e']);
    for (final s in [null, 'all']) {
      expect((await repo.listWhere({'client_ref': 'C1'}, status: s)).items.map((t) => t.id), contains('e'), reason: '$s');
    }
  });

  test('watchWhere takes the same arguments', () async {
    final seen = <List<String>>[];
    final sub = legacyRepo(legacyDb(rows)).watchWhere({}, mine: true, status: 'open').listen((p) => seen.add([for (final t in p.items) t.id]));
    await Future<void>.delayed(Duration.zero);
    await Future<void>.delayed(Duration.zero);
    await sub.cancel();
    expect(seen.single.toSet(), {'a', 'c'});
  });
}
