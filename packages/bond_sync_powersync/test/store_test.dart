import 'package:bond_sync/bond_sync.dart';
import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:powersync/powersync.dart';

import 'fake_sync_db.dart';

final _schema = Schema([
  const Table('notes', [Column.text('title'), Column.text('body')]),
  const Table('tasks', [Column.text('title'), Column.text('state')], trackMetadata: true),
  const Table('lists', [Column.text('name')]),
  const Table('items', [Column.text('list_id')]),
  ...syncSupportTables(),
]);

SyncPolicy _policy({
  Map<String, Set<String>?> createPuts = const {},
  Map<String, Set<String>?> silent = const {},
  Map<String, List<(String, String)>> rekey = const {},
}) =>
    SyncPolicy(schema: _schema, createPuts: createPuts, silentWrites: silent, rekeyChildren: rekey);

PowerSyncSyncStore _store(FakeSyncDb db, [SyncPolicy? policy]) =>
    PowerSyncSyncStore.withDb(db, policy: policy ?? _policy());

SyncCrudEntry _entry(int id, String op, String table, String rowId, {Map<String, Object?>? data, String? meta}) =>
    SyncCrudEntry(clientId: id, op: op, table: table, id: rowId, opData: data, metadata: meta);

SyncRejection _note(String op, String payload, {String table = 'notes', String? action}) => SyncRejection(
      id: 'r1',
      table: table,
      rowId: 'row1',
      action: action,
      code: 'invalid',
      message: null,
      payload: payload,
      createdAt: '2026-11-08T10:00:00.000Z',
      op: op,
    );

void main() {
  group('nextBatch', () {
    test('nothing queued is null', () async {
      expect(await _store(FakeSyncDb()).nextBatch(), isNull);
    });

    test('entries become numbered ops and complete is wired through', () async {
      final db = FakeSyncDb();
      final rig = CrudRig();
      db.crud.add(rig.tx([
        _entry(10, 'put', 'notes', 'a', data: {'title': 'x'}),
        _entry(11, 'patch', 'notes', 'a', data: {'title': 'y'}),
        _entry(12, 'delete', 'notes', 'a'),
      ], id: 5));
      final b = (await _store(db).nextBatch())!;
      expect(b.key, 'tx5');
      expect(b.transactionId, 5);
      expect(b.ops.map((o) => [o.seq, o.op, o.id]), [
        [0, 'put', 'a'],
        [1, 'patch', 'a'],
        [2, 'delete', 'a'],
      ]);
      expect(b.ops.last.data, isEmpty);
      await b.complete();
      expect(rig.completed, 1);
    });

    test('a write outside a transaction is keyed by its client id', () async {
      final db = FakeSyncDb();
      db.crud.add(CrudRig().tx([_entry(42, 'put', 'notes', 'a', data: {'title': 'x'})], id: null));
      final b = (await _store(db).nextBatch())!;
      expect(b.key, 'c42');
      expect(b.transactionId, isNull);
    });

    test('metadata names the action and extras ride in data; columns win', () async {
      final db = FakeSyncDb();
      db.crud.add(CrudRig().tx([
        _entry(1, 'patch', 'tasks', 't', data: {'state': 'done'}, meta: '{"action":"complete","note":"hi","state":"x"}'),
        _entry(2, 'patch', 'tasks', 't', data: {'state': 'open'}, meta: 'not json'),
      ]));
      final b = (await _store(db).nextBatch())!;
      expect(b.ops[0].action, 'complete');
      expect(b.ops[0].data, {'note': 'hi', 'state': 'done'});
      expect(b.ops[1].action, isNull);
      expect(b.ops[1].data, {'state': 'open'});
    });
  });

  group('applyVerdicts', () {
    const ok = SyncVerdict('ok', null, null);
    final now = DateTime.utc(2026, 11, 8, 10);
    SyncUploadOp op(int seq, String o, String table, String id, {String? action, Map<String, Object?> data = const {}}) =>
        SyncUploadOp(seq: seq, op: o, table: table, id: id, action: action, data: data);

    test('only accepted verdicts open no transaction', () async {
      final db = FakeSyncDb();
      await _store(db).applyVerdicts([op(0, 'put', 'notes', 'a')], {0: ok}, now);
      expect(db.transactions, 0);
      expect(db.statements, isEmpty);
    });

    test('a refused create removes the optimistic row and writes one note, in one transaction', () async {
      final db = FakeSyncDb();
      final s = _store(db, _policy(createPuts: {'notes': null}));
      await s.applyVerdicts(
        [op(0, 'put', 'notes', 'a', data: {'title': ''})],
        {0: const SyncVerdict('rejected', 'invalid', 'title_required')},
        now,
      );
      expect(db.transactions, 1);
      expect(db.statements.every((st) => st.inTx), isTrue);
      expect(db.where('DELETE FROM ps_data__notes WHERE id = ?').single.params, ['a']);
      expect(db.where('DELETE FROM ps_crud'), hasLength(1));
      final insert = db.where('INSERT INTO sync_rejections').single;
      expect(insert.params[1], 'notes');
      expect(insert.params[2], 'a');
      expect(insert.params[4], 'invalid');
      expect(insert.params[5], 'title_required');
      expect(insert.params[6], '{"title":""}');
      expect(insert.params[8], 'put');
    });

    test('a refused patch keeps the row and writes a note', () async {
      final db = FakeSyncDb();
      await _store(db).applyVerdicts(
        [op(0, 'patch', 'notes', 'a', data: {'title': 'x'})],
        {0: const SyncVerdict('rejected', 'forbidden', null)},
        now,
      );
      expect(db.where('DELETE FROM ps_data__'), isEmpty);
      expect(db.where('INSERT INTO sync_rejections'), hasLength(1));
      expect(db.where('UPDATE sync_rejections SET message'), hasLength(1));
    });

    test('a silent write leaves no note', () async {
      final db = FakeSyncDb();
      await _store(db, _policy(silent: {'notes': null})).applyVerdicts(
        [op(0, 'patch', 'notes', 'a')],
        {0: const SyncVerdict('rejected', 'forbidden', null)},
        now,
      );
      expect(db.where('sync_rejections'), isEmpty);
    });

    test('a failed removal still writes the note and says so', () async {
      final db = FakeSyncDb()..failWhen = (sql) => sql.startsWith('DELETE FROM ps_data__');
      await _store(db, _policy(createPuts: {'notes': null})).applyVerdicts(
        [op(0, 'put', 'notes', 'a', data: {'title': ''})],
        {0: const SyncVerdict('rejected', 'invalid', 'bad')},
        now,
      );
      expect(db.where('INSERT INTO sync_rejections').single.params[5], 'bad (the unsent row could not be removed)');
    });

    test('a re-key updates the row, queued writes and child rows', () async {
      final db = FakeSyncDb();
      await _store(db, _policy(rekey: {'lists': [('items', 'list_id')]})).applyVerdicts(
        [op(0, 'put', 'lists', 'L', data: {'name': 'x'})],
        {0: const SyncVerdict('ok', null, null, resolvedId: 'SRV')},
        now,
      );
      expect(db.where('UPDATE ps_data__lists SET id = ? WHERE id = ?').single.params, ['SRV', 'L']);
      expect(db.where("UPDATE ps_crud SET data = json_set(data, '\$.id'"), hasLength(1));
      expect(db.where('UPDATE ps_data__items SET data = json_set(data, \'\$.list_id\''), hasLength(1));
      expect(db.where("'\$.data.list_id'"), hasLength(1));
    });

    test('a re-key drops the stand-in when the server copy is already local', () async {
      final db = FakeSyncDb()..onGetOptional = (sql, p) => sql.contains('SELECT 1 AS x') ? {'x': 1} : null;
      await _store(db).applyVerdicts(
        [op(0, 'put', 'lists', 'L')],
        {0: const SyncVerdict('ok', null, null, resolvedId: 'SRV')},
        now,
      );
      expect(db.where('DELETE FROM ps_data__lists WHERE id = ?').single.params, ['L']);
      expect(db.where('UPDATE ps_data__lists SET id'), isEmpty);
    });

    test('table names outside the schema are never put into SQL', () async {
      final db = FakeSyncDb();
      await _store(db, _policy(createPuts: {'evil; DROP': null})).applyVerdicts(
        [op(0, 'put', 'evil; DROP', 'a')],
        {0: const SyncVerdict('rejected', 'invalid', null)},
        now,
      );
      expect(db.sqls.any((s) => s.contains('evil')), isFalse);
      expect(db.where('INSERT INTO sync_rejections'), hasLength(1));
    });
  });

  group('bookkeeping', () {
    test('meta read, write and delete', () async {
      final db = FakeSyncDb()..onGetOptional = (sql, p) => {'value': 'v1'};
      final s = _store(db);
      expect(await s.readMeta('k'), 'v1');
      await s.writeMeta('k', 'v2');
      await s.deleteMeta('k');
      expect(db.where('INSERT OR REPLACE INTO sync_meta').single.params, ['k', 'k', 'v2']);
      expect(db.where('DELETE FROM sync_meta').single.params, ['k']);
    });

    test('prune uses the keep window', () async {
      final db = FakeSyncDb();
      await _store(db).pruneRejections(DateTime.utc(2026, 11, 8));
      expect(db.where('DELETE FROM sync_rejections').single.params, [
        DateTime.utc(2026, 11, 8).subtract(kSyncRejectionKeep).toIso8601String(),
      ]);
    });

    test('rejections map rows and watch maps streams', () async {
      final row = {
        'id': 'r1',
        'table_name': 'notes',
        'row_id': 'a',
        'code': 'invalid',
        'created_at': '2026-11-08T10:00:00.000Z',
      };
      final db = FakeSyncDb()..onGetAll = (sql, p) => [row];
      final s = _store(db);
      expect((await s.rejections()).single.rowId, 'a');
      final next = s.watchRejections().first;
      db.watchController.add([row]);
      expect((await next).single.code, 'invalid');
      await s.clearRejection('r1');
      expect(db.where('DELETE FROM sync_rejections WHERE id').single.params, ['r1']);
    });

    test('rows reads schema tables only', () async {
      final db = FakeSyncDb()..onGetAll = (sql, p) => [{'id': 'a'}];
      final s = _store(db);
      expect(await s.rows('notes'), [{'id': 'a'}]);
      expect(db.sqls.last, 'SELECT * FROM notes');
      expect(() => s.rows('nope'), throwsArgumentError);
      expect(() => s.rows('notes; DROP'), throwsArgumentError);
    });
  });

  group('resend', () {
    test('a put merges the stored row under the payload and queues through the view', () async {
      final db = FakeSyncDb()..onGetOptional = (sql, p) => {'data': '{"title":"old","body":"keep","ghost":1}'};
      final r = await _store(db).resend(_note('put', '{"title":"fixed"}'));
      expect(r, SyncResendResult.queued);
      final ins = db.where('INSERT OR REPLACE INTO notes').single;
      expect(ins.sql, contains('(id, title, body)'));
      expect(ins.params, ['row1', 'fixed', 'keep']);
      expect(db.where('DELETE FROM sync_rejections WHERE id = ?'), hasLength(1));
    });

    test('a put on a metadata table carries the action', () async {
      final db = FakeSyncDb();
      await _store(db).resend(_note('put', '{"title":"t"}', table: 'tasks', action: 'create'));
      final ins = db.where('INSERT OR REPLACE INTO tasks').single;
      expect(ins.sql, contains('_metadata'));
      expect(ins.params.last, '{"action":"create"}');
    });

    test('a patch knocks the columns out first, then updates', () async {
      final db = FakeSyncDb()..onGetOptional = (sql, p) => {'x': 1};
      final r = await _store(db).resend(_note('patch', '{"title":"fixed"}'));
      expect(r, SyncResendResult.queued);
      expect(db.where('UPDATE ps_data__notes SET data = json_remove(data, ?)').single.params, [r'$.title', 'row1']);
      expect(db.where('UPDATE notes SET title = ?').single.params, ['fixed', 'row1']);
    });

    test('a patch for a row that is gone says so and keeps the note', () async {
      final db = FakeSyncDb();
      final r = await _store(db).resend(_note('patch', '{"title":"x"}'));
      expect(r, SyncResendResult.rowGone);
      expect(db.where('UPDATE sync_rejections SET message').single.params.last, 'r1');
      expect(db.where('DELETE FROM sync_rejections'), isEmpty);
    });

    test('unsupported: delete, unknown column, unknown table, empty payload', () async {
      final db = FakeSyncDb();
      final s = _store(db);
      expect(await s.resend(_note('delete', '{"a":1}')), SyncResendResult.unsupported);
      expect(await s.resend(_note('put', '{"nope":1}')), SyncResendResult.unsupported);
      expect(await s.resend(_note('put', '{"title":1}', table: 'ghost')), SyncResendResult.unsupported);
      expect(await s.resend(_note('put', '{}')), SyncResendResult.unsupported);
      expect(await s.resend(_note('put', 'garbage')), SyncResendResult.unsupported);
      expect(db.where('INSERT OR REPLACE'), isEmpty);
    });
  });
}
