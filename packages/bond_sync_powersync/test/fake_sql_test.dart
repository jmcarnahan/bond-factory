import 'package:bond_sync_powersync/testing.dart';
import 'package:flutter_test/flutter_test.dart';

FakeSyncDb db({Map<String, Set<String>> columns = const {}}) => FakeSyncDb.tables({
      't': [
        {'id': 'a', 'n': 3, 's': 'x', 'd': null},
        {'id': 'b', 'n': 1, 's': 'y', 'd': '2026'},
        {'id': 'c', 'n': 2, 's': 'x', 'd': '2025'},
      ],
    }, applySql: true, columns: columns);

Future<List<Object?>> ids(FakeSyncDb d, String sql, [List<Object?> p = const []]) async =>
    [for (final r in await d.getAll(sql, p)) r['id']];

void main() {
  test('applySql off keeps the old behaviour: writes recorded only, reads unfiltered', () async {
    final d = FakeSyncDb.tables({
      't': [
        {'id': 'a'},
        {'id': 'b'},
      ],
    });
    await d.execute('DELETE FROM t WHERE id = ?', ['a']);
    expect(d.tables['t'], hasLength(2));
    expect((await d.getAll('SELECT * FROM t WHERE id = ?', ['a'])), hasLength(2));
  });

  test('WHERE with AND, OR, parentheses, IS NULL, IN and comparisons', () async {
    final d = db();
    expect(await ids(d, 'SELECT * FROM t WHERE s = ? AND n > ?', ['x', 2]), ['a']);
    expect(await ids(d, 'SELECT * FROM t WHERE (s = ? OR id = ?) AND d IS NOT NULL', ['x', 'b']), ['b', 'c']);
    expect(await ids(d, 'SELECT * FROM t WHERE d IS NULL'), ['a']);
    expect(await ids(d, 'SELECT * FROM t WHERE id IN (?, ?)', ['a', 'c']), ['a', 'c']);
    expect(await ids(d, "SELECT * FROM t WHERE s != 'x'"), ['b']);
    expect(await ids(d, 'SELECT * FROM t WHERE d >= ?', ['2026']), ['b']);
  });

  test('ORDER BY with IS NULL, DESC and ties; LIMIT', () async {
    final d = db();
    expect(await ids(d, 'SELECT * FROM t ORDER BY d IS NULL, d'), ['c', 'b', 'a']);
    expect(await ids(d, 'SELECT * FROM t ORDER BY s, n DESC'), ['a', 'c', 'b']);
    expect(await ids(d, 'SELECT * FROM t ORDER BY n LIMIT 2'), ['b', 'c']);
  });

  test('INSERT, OR REPLACE, UPDATE, DELETE change the table and pulse changes', () async {
    final d = db();
    var pulses = 0;
    final sub = d.changes.stream.listen((_) => pulses++);
    await d.execute('INSERT INTO t (id, n) VALUES (?, ?)', ['e', 9]);
    await expectLater(d.execute('INSERT INTO t (id, n) VALUES (?, ?)', ['e', 9]), throwsStateError);
    await d.execute('INSERT OR REPLACE INTO t (id, n) VALUES (?, 5)', ['e']);
    await d.execute('UPDATE t SET n = ?, d = NULL WHERE id = ? AND s IS NULL', [0, 'e']);
    expect(d.tables['t']!.last, {'id': 'e', 'n': 0, 'd': null});
    await d.execute('DELETE FROM t WHERE n >= ?', [3]);
    await pumpEventQueue();
    await sub.cancel();
    expect(d.tables['t']!.map((r) => r['id']), ['b', 'c', 'e']);
    expect(pulses, 4);
  });

  test('declared columns are enforced and fill the inserted row', () async {
    final d = db(columns: {'t': {'id', 'n', 's', 'd'}});
    await expectLater(d.execute('UPDATE t SET nope = ? WHERE id = ?', [1, 'a']), throwsStateError);
    await expectLater(d.getAll('SELECT * FROM t WHERE nope = ?', [1]), throwsStateError);
    await d.execute('INSERT INTO t (id) VALUES (?)', ['z']);
    expect(d.tables['t']!.last, {'id': 'z', 'n': null, 's': null, 'd': null});
  });

  test('a shape the engine does not know fails loudly', () async {
    await expectLater(db().getAll('SELECT * FROM t WHERE id LIKE ?', ['a%']), throwsUnsupportedError);
  });
}
