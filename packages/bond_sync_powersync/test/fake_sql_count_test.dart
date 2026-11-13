import 'package:bond_sync_powersync/testing.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('COUNT(*) counts the matches and LIMIT n OFFSET m pages the ordered rows', () async {
    final d = FakeSyncDb.tables({
      't': [
        for (final (id, s) in [('a', 'x'), ('b', 'y'), ('c', 'x'), ('d', 'x')]) {'id': id, 's': s},
      ],
    }, applySql: true, columns: {'t': {'id', 's'}});
    expect((await d.getAll('SELECT COUNT(*) AS n FROM t WHERE s = ?', ['x'])).single, {'n': 3});
    expect((await d.getAll('SELECT COUNT(*) FROM t')).single, {'COUNT(*)': 4});
    final page = await d.getAll('SELECT * FROM t WHERE s = ? ORDER BY id LIMIT ? OFFSET ?', ['x', 2, 1]);
    expect([for (final r in page) r['id']], ['c', 'd']);
    expect(await d.getAll('SELECT * FROM t ORDER BY id LIMIT ? OFFSET ?', [5, 9]), isEmpty);
  });
}
