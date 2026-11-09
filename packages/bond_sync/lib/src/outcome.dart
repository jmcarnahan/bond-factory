/// What a store must do with the verdicts of one upload. Pure: every
/// [SyncStore] (the fake and the database adapter) runs the same plan.
library;

import 'models.dart';
import 'verdicts.dart';

/// The app's rules for refusals. Table and column names, never read from the server.
class OutcomeRules {
  const OutcomeRules({
    this.createPuts = const {},
    this.silentWrites = const {},
    this.rekeyChildren = const {},
  });

  /// Puts that CREATE a row the server may not have; a refusal removes the
  /// optimistic local row. The value is the set of actions, or null for any.
  final Map<String, Set<String>?> createPuts;

  /// Writes whose refusal leaves nothing for the person to do, so no note is
  /// kept: table -> actions (null = every action).
  final Map<String, Set<String>?> silentWrites;

  /// When the server re-keys a row, the child columns that name it:
  /// table -> [(childTable, column)].
  final Map<String, List<(String, String)>> rekeyChildren;

  bool isSilentWrite({required String table, String? action}) {
    if (!silentWrites.containsKey(table)) return false;
    final actions = silentWrites[table];
    return actions == null || (action != null && actions.contains(action));
  }

  bool createsRow(SyncUploadOp op) {
    if (op.op != 'put' || !createPuts.containsKey(op.table)) return false;
    final actions = createPuts[op.table];
    return actions == null || op.action == null || actions.contains(op.action);
  }
}

/// A row the server gave another primary key.
class Rekey {
  const Rekey(this.op, this.newId);
  final SyncUploadOp op;
  final String newId;
}

/// One refused write: remove the optimistic row, keep a note, or both.
class Refusal {
  const Refusal(this.op, this.verdict, this.stamp, {required this.removeRow, required this.keepNote});

  final SyncUploadOp op;
  final SyncVerdict verdict;

  /// One millisecond apart, in the transaction's order, so the notes of one
  /// upload keep that order when listed or resent.
  final DateTime stamp;

  /// The put CREATED the row and was refused: the local row never reached the server.
  final bool removeRow;

  /// False for a silent write.
  final bool keepNote;
}

class OutcomePlan {
  const OutcomePlan(this.rekeys, this.refusals);
  final List<Rekey> rekeys;
  final List<Refusal> refusals;
  bool get isEmpty => rekeys.isEmpty && refusals.isEmpty;
}

/// Plans the local changes for [verdicts] over [ops]. When a create is refused,
/// later refused writes to the same row are a consequence, not a second cause:
/// one note covers both.
OutcomePlan planOutcome(
  List<SyncUploadOp> ops,
  Map<int, SyncVerdict> verdicts,
  DateTime now, {
  OutcomeRules rules = const OutcomeRules(),
}) {
  final rekeys = <Rekey>[
    for (final op in ops)
      if (verdicts[op.seq] case final v?
          when v.isOk && v.resolvedId != null && v.resolvedId != op.id)
        Rekey(op, v.resolvedId!),
  ];
  final refusals = <Refusal>[];
  final dead = <String, int>{};
  var i = 0;
  for (final op in ops) {
    final v = verdicts[op.seq];
    if (v == null || !v.needsAction) continue;
    final deadSeq = dead['${op.table}\u0000${op.id}'];
    if (deadSeq != null && op.seq > deadSeq) continue;
    final remove = v.isRejected && rules.createsRow(op);
    if (remove) dead['${op.table}\u0000${op.id}'] = op.seq;
    refusals.add(Refusal(
      op,
      v,
      now.add(Duration(milliseconds: i++)),
      removeRow: remove,
      keepNote: !rules.isSilentWrite(table: op.table, action: op.action),
    ));
  }
  return OutcomePlan(rekeys, refusals);
}
