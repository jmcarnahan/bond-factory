import 'package:bond_sync/bond_sync.dart';
import 'package:bond_sync/testing.dart';
import 'package:test/test.dart';

void main() {
  test('writes queue one transaction each; transaction() groups them', () async {
    final s = FakeSyncStore();
    s.put('notes', 'a', {'title': 'a'});
    s.transaction(() {
      s.patch('notes', 'a', {'title': 'b'});
      s.delete('notes', 'a');
    });
    expect(s.queuedOps, 3);
    final first = (await s.nextBatch())!;
    expect(first.ops.single.op, 'put');
    await first.complete();
    final second = (await s.nextBatch())!;
    expect(second.ops.map((o) => [o.seq, o.op]), [
      [0, 'patch'],
      [1, 'delete'],
    ]);
    await second.complete();
    expect(await s.nextBatch(), isNull);
  });

  test('coalesce merges the queue into one batch with unique seq and completes it all', () async {
    final s = FakeSyncStore(coalesce: true);
    s.put('notes', 'a', {'title': 'a'});
    s.put('notes', 'b', {'title': 'b'});
    s.patch('notes', 'a', {'title': 'c'});
    final b = (await s.nextBatch())!;
    expect(b.ops.map((o) => o.seq), [0, 1, 2]);
    expect(b.ops.map((o) => o.id), ['a', 'b', 'a']);
    s.put('notes', 'late', {'title': 'x'}); // written while the batch is out
    await b.complete();
    expect(s.queued.map((o) => o.id), ['late']);
  });

  test('rows reflect put, patch, delete and server rows', () async {
    final s = FakeSyncStore();
    s.put('notes', 'a', {'title': 'a'});
    s.patch('notes', 'a', {'body': 'x'});
    s.putFromServer('notes', 'z', {'title': 'z'});
    expect((await s.rows('notes')).map((r) => r['id']), ['a', 'z']);
    expect((await s.rows('notes')).first, {'id': 'a', 'title': 'a', 'body': 'x'});
    s.delete('notes', 'a');
    expect(await s.rows('notes'), hasLength(1));
    expect(s.queued.last.data, isEmpty);
  });

  test('a re-key follows the queued writes and child rows', () async {
    final s = FakeSyncStore(rules: const OutcomeRules(rekeyChildren: {'lists': [('items', 'list_id')]}));
    s.put('lists', 'L', {'name': 'x'});
    s.put('items', 'i1', {'list_id': 'L'});
    final batch = (await s.nextBatch())!;
    await s.applyVerdicts(batch.ops, {0: const SyncVerdict('ok', null, null, resolvedId: 'SRV')}, DateTime.utc(2026));
    expect((await s.rows('lists')).single['id'], 'SRV');
    expect((await s.rows('items')).single['list_id'], 'SRV');
    expect(s.queued.last.data['list_id'], 'SRV');
  });

  test('a re-key drops the stand-in when the server copy is already here', () async {
    final s = FakeSyncStore();
    s.put('notes', 'a', {'title': 'local'});
    s.putFromServer('notes', 'SRV', {'title': 'server'});
    final batch = (await s.nextBatch())!;
    await s.applyVerdicts(batch.ops, {0: const SyncVerdict('ok', null, null, resolvedId: 'SRV')}, DateTime.utc(2026));
    expect(await s.rows('notes'), [
      {'id': 'SRV', 'title': 'server'},
    ]);
  });

  test('the same refusal twice keeps one note with the newest text', () async {
    final s = FakeSyncStore();
    s.put('notes', 'a', {'title': ''});
    final ops = (await s.nextBatch())!.ops;
    await s.applyVerdicts(ops, {0: const SyncVerdict('rejected', 'invalid', 'first')}, DateTime.utc(2026));
    await s.applyVerdicts(ops, {0: const SyncVerdict('rejected', 'invalid', 'second')}, DateTime.utc(2026, 1, 2));
    final notes = await s.rejections();
    expect(notes, hasLength(1));
    expect(notes.single.message, 'second');
  });

  test('old notes are pruned', () async {
    final s = FakeSyncStore();
    s.put('notes', 'a', {'title': ''});
    final ops = (await s.nextBatch())!.ops;
    await s.applyVerdicts(ops, {0: const SyncVerdict('rejected', 'invalid', null)}, DateTime.utc(2026, 1, 1));
    await s.pruneRejections(DateTime.utc(2026, 1, 20));
    expect(await s.rejections(), hasLength(1));
    await s.pruneRejections(DateTime.utc(2026, 3, 1));
    expect(await s.rejections(), isEmpty);
  });

  test('watchRejections emits now and after changes', () async {
    final s = FakeSyncStore();
    final seen = <int>[];
    final sub = s.watchRejections().listen((l) => seen.add(l.length));
    await Future<void>.delayed(Duration.zero);
    s.put('notes', 'a', {'title': ''});
    final ops = (await s.nextBatch())!.ops;
    await s.applyVerdicts(ops, {0: const SyncVerdict('rejected', 'invalid', null)}, DateTime.utc(2026));
    await Future<void>.delayed(Duration.zero);
    await s.clearRejection((await s.rejections()).single.id);
    await Future<void>.delayed(Duration.zero);
    await sub.cancel();
    expect(seen, [0, 1, 0]);
  });

  test('resend: rowGone for a deleted row, unsupported for a delete or empty payload', () async {
    final s = FakeSyncStore();
    SyncRejection note(String op, String? payload) => SyncRejection(
          id: 'r', table: 'notes', rowId: 'a', action: null, code: 'x', message: null,
          payload: payload, createdAt: '2026-01-01T00:00:00.000Z', op: op,
        );
    expect(await s.resend(note('delete', '{"a":1}')), SyncResendResult.unsupported);
    expect(await s.resend(note('put', null)), SyncResendResult.unsupported);
    expect(await s.resend(note('put', '{}')), SyncResendResult.unsupported);
    expect(await s.resend(note('patch', '{"title":"x"}')), SyncResendResult.rowGone);
  });

  test('Rejections reads one row and clears', () async {
    final s = FakeSyncStore();
    s.put('notes', 'a', {'title': ''});
    s.put('notes', 'b', {'title': ''});
    for (var i = 0; i < 2; i++) {
      final b = (await s.nextBatch())!;
      await s.applyVerdicts(b.ops, {0: const SyncVerdict('rejected', 'invalid', null)}, DateTime.utc(2026));
      await b.complete();
    }
    final r = Rejections(s);
    expect(await r.all(), hasLength(2));
    expect(await r.forRow('notes', 'a'), hasLength(1));
    await r.clearAll();
    expect(await r.all(), isEmpty);
  });
}
