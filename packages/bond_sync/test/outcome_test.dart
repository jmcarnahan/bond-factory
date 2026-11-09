import 'dart:convert';

import 'package:bond_sync/bond_sync.dart';
import 'package:test/test.dart';

SyncUploadOp _op(int seq, String op, String table, String id, {String? action, Map<String, Object?>? data}) =>
    SyncUploadOp(seq: seq, op: op, table: table, id: id, action: action, data: data ?? const {});

final _now = DateTime.utc(2026, 11, 8);

void main() {
  test('ok and replayed verdicts plan nothing', () {
    final p = planOutcome(
      [_op(0, 'put', 'notes', 'a'), _op(1, 'put', 'notes', 'b')],
      {0: const SyncVerdict('ok', null, null), 1: const SyncVerdict('skipped', 'already', null)},
      _now,
    );
    expect(p.isEmpty, isTrue);
  });

  test('a resolved id different from the op id is a re-key', () {
    final p = planOutcome(
      [_op(0, 'put', 'notes', 'a'), _op(1, 'put', 'notes', 'b')],
      {
        0: const SyncVerdict('ok', null, null, resolvedId: 'srv'),
        1: const SyncVerdict('ok', null, null, resolvedId: 'b'),
      },
      _now,
    );
    expect(p.rekeys.map((r) => r.newId), ['srv']);
  });

  test('notes are stamped one millisecond apart in order', () {
    final p = planOutcome(
      [_op(0, 'patch', 'notes', 'a'), _op(1, 'patch', 'notes', 'b')],
      {0: const SyncVerdict('rejected', 'forbidden', null), 1: const SyncVerdict('rejected', 'forbidden', null)},
      _now,
    );
    expect(p.refusals[1].stamp.difference(p.refusals[0].stamp), const Duration(milliseconds: 1));
  });

  test('a refused create removes the row and one note covers later writes', () {
    const rules = OutcomeRules(createPuts: {'notes': null});
    final p = planOutcome(
      [_op(0, 'put', 'notes', 'a'), _op(1, 'patch', 'notes', 'a'), _op(2, 'patch', 'notes', 'other')],
      {for (var i = 0; i < 3; i++) i: const SyncVerdict('rejected', 'invalid', null)},
      _now,
      rules: rules,
    );
    expect(p.refusals.map((r) => r.op.seq), [0, 2]);
    expect(p.refusals.first.removeRow, isTrue);
    expect(p.refusals.last.removeRow, isFalse);
  });

  test('createsRow honours the action set', () {
    const rules = OutcomeRules(createPuts: {'tasks': {'create'}});
    expect(rules.createsRow(_op(0, 'put', 'tasks', 'a', action: 'create')), isTrue);
    expect(rules.createsRow(_op(0, 'put', 'tasks', 'a', action: 'reopen')), isFalse);
    expect(rules.createsRow(_op(0, 'patch', 'tasks', 'a', action: 'create')), isFalse);
    expect(rules.createsRow(_op(0, 'put', 'notes', 'a')), isFalse);
  });

  test('a skipped (not already) op still needs action but never removes a row', () {
    const rules = OutcomeRules(createPuts: {'notes': null});
    final p = planOutcome(
      [_op(0, 'put', 'notes', 'a')],
      {0: const SyncVerdict('skipped', 'other', null)},
      _now,
      rules: rules,
    );
    expect(p.refusals.single.removeRow, isFalse);
  });

  test('silent writes keep no note but still remove', () {
    const rules = OutcomeRules(createPuts: {'c': null}, silentWrites: {'c': null});
    final p = planOutcome(
      [_op(0, 'put', 'c', 'a')],
      {0: const SyncVerdict('rejected', 'forbidden', null)},
      _now,
      rules: rules,
    );
    expect(p.refusals.single.keepNote, isFalse);
    expect(p.refusals.single.removeRow, isTrue);
  });

  test('chunkOps by count, bytes and per-kind cap', () {
    final ops = [for (var i = 0; i < 5; i++) _op(i, 'put', 'notes', 'n$i', data: {'t': 'x'})];
    expect(chunkOps(ops, const UploadLimits(chunkSize: 2)).map((c) => c.length), [2, 2, 1]);
    expect(chunkOps(ops, const UploadLimits(chunkBytes: 1)).map((c) => c.length), [1, 1, 1, 1, 1]);
    expect(chunkOps(ops, const UploadLimits(sendCaps: {'notes:': 3})).map((c) => c.length), [3, 2]);
    expect(chunkOps(const [], const UploadLimits()), isEmpty);
  });

  test('chunkOps at the exact default byte boundary', () {
    // The chunker counts each op as its JSON bytes plus one separator.
    int size(SyncUploadOp o) => utf8.encode(jsonEncode(o.toJson())).length + 1;
    SyncUploadOp padded(int seq, int pad) =>
        _op(seq, 'put', 'notes', 'n$seq', data: {'body': 'x' * pad});
    final base = size(padded(0, 0));
    const half = 512 * 1024 ~/ 2;
    final exact = [padded(0, half - base), padded(1, half - base)];
    expect(exact.fold<int>(0, (n, o) => n + size(o)), 512 * 1024);
    expect(chunkOps(exact, const UploadLimits()).map((c) => c.length), [2]);

    final oneOver = [padded(0, half - base), padded(1, half - base + 1)];
    expect(oneOver.fold<int>(0, (n, o) => n + size(o)), 512 * 1024 + 1);
    expect(chunkOps(oneOver, const UploadLimits()).map((c) => c.length), [1, 1]);

    // a third op after an exactly full chunk starts a new one
    expect(chunkOps([...exact, padded(2, 0)], const UploadLimits()).map((c) => c.length), [2, 1]);
  });

  test('chunkOps keeps order and loses nothing', () {
    final ops = [for (var i = 0; i < 250; i++) _op(i, 'put', 'notes', 'n$i')];
    final chunks = chunkOps(ops, const UploadLimits());
    expect(chunks.map((c) => c.length), [100, 100, 50]);
    expect([for (final c in chunks) ...c.map((o) => o.seq)], [for (var i = 0; i < 250; i++) i]);
  });
}
