/// Chunking and verdict handling of queued writes against a [SyncStore] and a
/// [SyncTransport]. The connector of a database adapter calls [uploadNext].
library;

import 'chunker.dart';
import 'failure.dart';
import 'limits.dart';
import 'models.dart';
import 'outcome.dart';
import 'server_clock.dart';
import 'store.dart';
import 'transient.dart';
import 'transport.dart';
import 'verdicts.dart';

/// The upload could not finish and must be tried again later (the SDK backs
/// off and calls again). Never thrown for a permanent outcome.
class SyncRetryLater implements Exception {
  const SyncRetryLater({this.counted = false});

  /// Counts toward giving the transaction up.
  final bool counted;

  @override
  String toString() => 'SyncRetryLater(counted: $counted)';
}

/// One op and what became of it.
class UploadOutcome {
  const UploadOutcome(this.op, this.verdict, {required this.sent});
  final SyncUploadOp op;
  final SyncVerdict verdict;

  /// False when the verdict was decided on the device (unsupported table, empty patch, given up).
  final bool sent;
}

class UploadSummary {
  const UploadSummary({this.outcomes = const [], this.batches = 0, this.gaveUp = false, this.retryLater});

  final List<UploadOutcome> outcomes;

  /// Transactions completed.
  final int batches;

  /// A transaction was refused after too many counted failures.
  final bool gaveUp;

  /// Set when [SyncUploader.uploadPending] stopped to retry later.
  final SyncRetryLater? retryLater;

  int get ok => outcomes.where((o) => o.verdict.isOk).length;
  int get rejected => outcomes.where((o) => o.verdict.isRejected).length;
  int get skipped => outcomes.where((o) => o.verdict.status == 'skipped').length;
  bool get isEmpty => outcomes.isEmpty;

  UploadOutcome? outcomeFor(int seq) {
    for (final o in outcomes) {
      if (o.op.seq == seq) return o;
    }
    return null;
  }
}

/// Outcome rules (the contract with the upload route):
///  * HTTP 200: `ok` leaves the row to sync back (`resolved_id` re-keys it);
///    `rejected` and `skipped` leave a note (a replay the server already has,
///    `skipped`/`already`, is silent) and a rejected PUT that created a row
///    removes the optimistic row; then the transaction completes.
///  * `permanent` failures refuse the whole chunk (`upload_rejected`).
///  * `offline`, `transientNoCount`, an unrenewable 401 and a `rate_limited`
///    verdict: [SyncRetryLater], never counted.
///  * `transientCounted` and a surprise: [SyncRetryLater] counted. After
///    `limits.transientMaxCount` counted failures spanning
///    `limits.transientMaxSpan` the unanswered ops are refused (`server_error`).
class SyncUploader {
  SyncUploader({
    required this.store,
    required this.transport,
    required this.clock,
    this.mapFailure = mapSyncFailure,
    this.limits = const UploadLimits(),
    this.rules = const OutcomeRules(),
    this.sendableTables,
    this.onServerNow,
  }) : _tracker = TransientTracker(store, limits, clock);

  final SyncStore store;
  final SyncTransport transport;
  final ServerClock clock;
  final FailureMapper mapFailure;
  final UploadLimits limits;
  final OutcomeRules rules;

  /// Tables that go through the upload route; null means every table.
  final Set<String>? sendableTables;

  /// Told the server's clock after every answer that carries it.
  final void Function(DateTime serverNow)? onServerNow;

  final TransientTracker _tracker;

  /// Verdicts the server gave per transaction key, kept until the
  /// transaction completes (the key is stable across attempts).
  final Map<String, Map<int, SyncVerdict>> _answered = {};

  /// Uploads batches until the queue is empty or an upload must be retried;
  /// the retry is reported in [UploadSummary.retryLater], never thrown.
  Future<UploadSummary> uploadPending({int maxBatches = 1000}) async {
    final outcomes = <UploadOutcome>[];
    var batches = 0;
    var gaveUp = false;
    SyncRetryLater? retry;
    try {
      while (batches < maxBatches) {
        final s = await uploadNext();
        if (s == null) break;
        batches += 1;
        outcomes.addAll(s.outcomes);
        gaveUp = gaveUp || s.gaveUp;
      }
    } on SyncRetryLater catch (r) {
      retry = r;
    }
    return UploadSummary(outcomes: outcomes, batches: batches, gaveUp: gaveUp, retryLater: retry);
  }

  /// Uploads the oldest queued transaction. Null when nothing waits. Throws
  /// [SyncRetryLater] for every outcome that should be retried.
  Future<UploadSummary?> uploadNext() async {
    try {
      await store.pruneRejections(clock.phoneNow());
    } catch (_) {}
    final batch = await store.nextBatch();
    if (batch == null) return null;
    final verdicts = <int, SyncVerdict>{};
    final local = <int>{};
    try {
      try {
        await _answerBatch(batch, verdicts, local);
        return await _finish(batch, verdicts, local, gaveUp: false);
      } on SyncRetryLater {
        rethrow;
      } catch (_) {
        throw const SyncRetryLater(counted: true); // a surprise counts against the transaction
      }
    } on SyncRetryLater catch (t) {
      if (!t.counted || batch.ops.isEmpty || !await _tracker.countAndCheck(batch.key)) rethrow;
      for (final e in (_answered[batch.key] ?? const <int, SyncVerdict>{}).entries) {
        verdicts.putIfAbsent(e.key, () => e.value);
      }
      for (final op in batch.ops) {
        if (verdicts.containsKey(op.seq)) continue;
        local.add(op.seq);
        verdicts[op.seq] = const SyncVerdict('rejected', 'server_error', 'The server could not take this change.');
      }
      return _finish(batch, verdicts, local, gaveUp: true);
    }
  }

  Future<void> _answerBatch(SyncBatch batch, Map<int, SyncVerdict> verdicts, Set<int> local) async {
    final sendable = <SyncUploadOp>[];
    for (final op in batch.ops) {
      if (sendableTables != null && !sendableTables!.contains(op.table)) {
        local.add(op.seq);
        verdicts[op.seq] = const SyncVerdict('rejected', 'unsupported', 'This change is sent another way.');
      } else if (op.op == 'patch' && op.data.isEmpty) {
        // Nothing changed: nothing to send, and the server would call it invalid.
        local.add(op.seq);
        verdicts[op.seq] = const SyncVerdict('skipped', 'already', null);
      } else {
        sendable.add(op);
      }
    }
    final pending = <SyncUploadOp>[];
    for (final op in sendable) {
      final known = _answered[batch.key]?[op.seq];
      if (known != null) {
        verdicts[op.seq] = known;
      } else {
        pending.add(op);
      }
    }
    for (final chunk in chunkOps(pending, limits)) {
      final answered = await _sendChunk(batch.transactionId, chunk);
      verdicts.addAll(answered);
      _answered.putIfAbsent(batch.key, () => {}).addAll(answered);
    }
    // A rate-limited op got no verdict: it is retried, never refused.
    if (sendable.any((o) => !verdicts.containsKey(o.seq))) throw const SyncRetryLater();
  }

  Future<UploadSummary> _finish(
    SyncBatch batch,
    Map<int, SyncVerdict> verdicts,
    Set<int> local, {
    required bool gaveUp,
  }) async {
    await store.applyVerdicts(batch.ops, verdicts, clock.phoneNow());
    await _tracker.forget(batch.key);
    await batch.complete();
    _answered.remove(batch.key);
    return UploadSummary(
      outcomes: [
        for (final op in batch.ops)
          if (verdicts[op.seq] case final v?) UploadOutcome(op, v, sent: !local.contains(op.seq)),
      ],
      batches: 1,
      gaveUp: gaveUp,
    );
  }

  void _noteNow(DateTime t) {
    clock.note(t);
    onServerNow?.call(t);
  }

  /// Sends one chunk; returns a verdict per answered op.
  Future<Map<int, SyncVerdict>> _sendChunk(int? transactionId, List<SyncUploadOp> chunk) async {
    Future<UploadResponse> send() => transport.upload(UploadRequest(transactionId: transactionId, ops: chunk));

    UploadResponse result;
    try {
      try {
        result = await send();
      } catch (e) {
        if (e is SyncRetryLater || mapFailure(e) != SyncFailure.unauthorized) rethrow;
        // Renew the session and send again once. Never sign out.
        if (await transport.refreshSession() != SessionRefresh.renewed) throw const SyncRetryLater();
        result = await send();
      }
    } on SyncRetryLater {
      rethrow;
    } catch (e) {
      switch (mapFailure(e)) {
        case SyncFailure.offline || SyncFailure.unauthorized || SyncFailure.transientNoCount:
          throw const SyncRetryLater();
        case SyncFailure.permanent:
          return {
            for (final op in chunk)
              op.seq: const SyncVerdict('rejected', 'upload_rejected', 'The server refused this change.'),
          };
        case SyncFailure.transientCounted:
          throw const SyncRetryLater(counted: true);
      }
    }

    final now = result.serverNow;
    if (now != null) _noteNow(now);
    final bySeq = {for (final r in result.results) r.seq: r};
    final out = <int, SyncVerdict>{};
    for (final op in chunk) {
      final r = bySeq[op.seq];
      // An answer that skips an op is not one to act on.
      if (r == null) throw const SyncRetryLater(counted: true);
      if (r.status == 'rejected' && r.code == 'rate_limited') continue;
      out[op.seq] = SyncVerdict(r.status, r.code, r.message, resolvedId: r.resolvedId);
    }
    return out;
  }
}
