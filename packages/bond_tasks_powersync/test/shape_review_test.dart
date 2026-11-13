import 'package:powersync/powersync.dart' show Column;
import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_powersync/bond_tasks_powersync.dart';
import 'package:flutter_test/flutter_test.dart';

import 'shape_support.dart';

List<String> writeSql(dynamic db) => [
      for (final s in db.statements)
        if (RegExp(r'^(INSERT|UPDATE|DELETE)').hasMatch(s.sql as String)) s.sql as String,
    ];

void main() {
  test('blank cells: notes only for the empty string, the others for any blank', () {
    final t = taskFromRow(legacyRow('a', {'notes': '  ', 'assigned_user_id': '  ', 'due_date': ' ', 'due_time': ' '}), nowUtc: t0, shape: legacyShape);
    expect(t.notes, '  ');
    expect((t.assignedUserId, t.dueDate, t.dueTime), (null, null, null));
    expect(taskFromRow(legacyRow('b', {'notes': ''}), nowUtc: t0, shape: legacyShape).notes, isNull);
  });

  group('prepare limits', () {
    test('a create whose prepare drops a required column throws and writes nothing', () async {
      for (final out in [<String, Object?>{}, {'title': 'only a title'}]) {
        final db = legacyDb([]);
        final repo = legacyRepo(db, prepare: (tx, w) async => out);
        await expectLater(repo.create(const TaskDraft(title: 'N', id: 'n')), throwsArgumentError);
        expect(writeSql(db), isEmpty);
        expect(db.tables['tasks'], isEmpty);
      }
    });

    test('an update whose prepare adds or changes status, completed_at or completed_by throws and writes nothing', () async {
      for (final k in ['status', 'completed_at', 'completed_by']) {
        final db = legacyDb([legacyRow('a')]);
        final repo = legacyRepo(db, prepare: (tx, w) async => {...w.values, k: 'x'});
        await expectLater(repo.update('a', const TaskPatch(title: 'T')), throwsArgumentError, reason: k);
        expect(writeSql(db), isEmpty, reason: k);
      }
    });
  });

  test('the repository copies the shape and extraColumns: changing the caller\'s collections later changes no SQL', () async {
    final absent = {...legacyShape.absent};
    final rename = {...legacyShape.rename};
    final extras = {...legacyExtras};
    final db = legacyDb([]);
    final repo = legacyRepo(db, shape: TaskTableShape(absent: absent, rename: rename), extraColumns: extras);
    absent.clear();
    rename['mirror_enabled'] = 'other';
    rename['title'] = 'heading';
    extras.add('bogus');
    await repo.create(const TaskDraft(title: 'N', id: 'n', priority: TaskPriority.high, extras: {'client_ref': 'C', 'bogus': 1}));
    final sql = writeSql(db).single;
    expect(sql, contains('sync_to_calendar'));
    expect(sql, isNot(contains('priority')));
    expect(sql, isNot(contains('heading')));
    expect(sql, isNot(contains('bogus')));
    expect(() => repo.shape.absent.add('x'), throwsUnsupportedError);
    expect(() => (repo.extraColumns).add('x'), throwsUnsupportedError);
  });

  test('names SQLite refuses unquoted are rejected as local and extra column names; names it accepts are not', () {
    for (final k in ['order', 'index', 'group', 'case', 'select', 'limit', 'values', 'where']) {
      expect(() => TaskTableShape(rename: {'source': k}).check(const {}), throwsArgumentError, reason: k);
      expect(() => PowerSyncTaskRepository(legacyDb([]), userId: 'u', extraColumns: {k}), throwsArgumentError, reason: k);
      expect(() => tasksTables(extraColumns: [Column.text(k)]), throwsArgumentError, reason: k);
    }
    for (final k in ['key', 'end', 'by', 'offset', 'column', 'like']) {
      TaskTableShape(rename: {'source': k}).check(const {});
      PowerSyncTaskRepository(legacyDb([]), userId: 'u', extraColumns: {k});
      tasksTables(extraColumns: [Column.text(k)]);
    }
  });

  test('negative limit or offset: watchWhere throws at call time, listWhere fails', () async {
    final repo = legacyRepo(legacyDb([legacyRow('a')]));
    expect(() => repo.watchWhere({'client_ref': 'C'}, limit: -1), throwsArgumentError);
    expect(() => repo.watchWhere({'client_ref': 'C'}, offset: -1), throwsArgumentError);
    await expectLater(repo.listWhere({'client_ref': 'C'}, limit: -1), throwsArgumentError);
  });
}
