import 'package:bond_api/bond_api.dart';
import 'package:bond_sync/bond_sync.dart';
import 'package:bond_sync/testing.dart';
import 'package:test/test.dart';

class _Rig {
  _Rig({
    UploadLimits limits = const UploadLimits(),
    OutcomeRules rules = const OutcomeRules(),
    Set<String>? sendable,
  }) {
    store = FakeSyncStore(rules: rules);
    uploader = SyncUploader(
      store: store,
      transport: transport,
      clock: clock,
      limits: limits,
      rules: rules,
      sendableTables: sendable,
      onServerNow: (t) => told = t,
    );
  }

  DateTime t = DateTime.utc(2026, 11, 8, 10);
  late final ServerClock clock = ServerClock(() => t);
  final FakeSyncTransport transport = FakeSyncTransport();
  late final FakeSyncStore store;
  late final SyncUploader uploader;
  DateTime? told;
}

UploadResponse _res(List<SyncOpResult> r, [DateTime? now]) => UploadResponse(results: r, serverNow: now);
SyncOpResult _r(int seq, String status, {String? code, String? message, String? resolved}) =>
    SyncOpResult(seq: seq, status: status, code: code, message: message, resolvedId: resolved);

void main() {
  test('an empty queue uploads nothing', () async {
    final rig = _Rig();
    expect(await rig.uploader.uploadNext(), isNull);
    expect((await rig.uploader.uploadPending()).isEmpty, isTrue);
    expect(rig.transport.uploads, isEmpty);
  });

  test('accepted writes complete the transaction', () async {
    final rig = _Rig();
    rig.store.put('notes', 'n1', {'title': 'a'});
    final s = (await rig.uploader.uploadNext())!;
    expect(s.ok, 1);
    expect(s.outcomes.single.sent, isTrue);
    expect(rig.store.queuedOps, 0);
    expect(rig.transport.uploads.single.transactionId, 1);
    expect(rig.transport.uploads.single.ops.single.toJson()['table'], 'notes');
  });

  test('server_now goes to the clock and the host', () async {
    final rig = _Rig();
    rig.store.put('notes', 'n1', {'title': 'a'});
    rig.transport.enqueueUpload(_res([_r(0, 'ok')], DateTime.utc(2026, 11, 8, 10, 0, 42)));
    await rig.uploader.uploadNext();
    expect(rig.clock.skew, const Duration(seconds: 42));
    expect(rig.told, DateTime.utc(2026, 11, 8, 10, 0, 42));
  });

  test('a rejected create removes the optimistic row and keeps a note', () async {
    final rig = _Rig(rules: const OutcomeRules(createPuts: {'notes': null}));
    rig.store.put('notes', 'n1', {'title': ''});
    rig.transport.enqueueUpload(_res([_r(0, 'rejected', code: 'invalid', message: 'title is required')]));
    final s = (await rig.uploader.uploadNext())!;
    expect(s.rejected, 1);
    expect(await rig.store.rows('notes'), isEmpty);
    final notes = await Rejections(rig.store).all();
    expect(notes.single.code, 'invalid');
    expect(notes.single.message, 'title is required');
    expect(rig.store.queuedOps, 0);
  });

  test('a resolved_id re-keys the local row', () async {
    final rig = _Rig();
    rig.store.put('notes', 'n1', {'title': 'a'});
    rig.transport.enqueueUpload(_res([_r(0, 'ok', resolved: 'srv-9')]));
    await rig.uploader.uploadNext();
    expect((await rig.store.rows('notes')).single['id'], 'srv-9');
  });

  test('skipped/already is silent', () async {
    final rig = _Rig();
    rig.store.put('notes', 'n1', {'title': 'a'});
    rig.transport.enqueueUpload(_res([_r(0, 'skipped', code: 'already')]));
    final s = (await rig.uploader.uploadNext())!;
    expect(s.skipped, 1);
    expect(await rig.store.rejections(), isEmpty);
  });

  test('a silent write keeps no note', () async {
    final rig = _Rig(rules: const OutcomeRules(silentWrites: {'cursors': null}));
    rig.store.put('cursors', 'c1', {'up_to': 3});
    rig.transport.enqueueUpload(_res([_r(0, 'rejected', code: 'forbidden')]));
    await rig.uploader.uploadNext();
    expect(await rig.store.rejections(), isEmpty);
    expect(rig.store.queuedOps, 0);
  });

  test('offline retries later and keeps the queue', () async {
    final rig = _Rig();
    rig.store.put('notes', 'n1', {'title': 'a'});
    rig.transport.enqueueUpload(const NetworkFailure(NetworkFailureKind.noAnswer, baseUrl: 'x'));
    await expectLater(
      rig.uploader.uploadNext(),
      throwsA(isA<SyncRetryLater>().having((e) => e.counted, 'counted', isFalse)),
    );
    expect(rig.store.queuedOps, 1);
    expect(rig.store.meta, isEmpty);
  });

  test('a 401 renews the session once and sends again', () async {
    final rig = _Rig();
    rig.store.put('notes', 'n1', {'title': 'a'});
    rig.transport.enqueueUpload(const Unauthorized());
    await rig.uploader.uploadNext();
    expect(rig.transport.refreshCalls, 1);
    expect(rig.transport.uploads, hasLength(2));
    expect(rig.store.queuedOps, 0);
  });

  test('a 401 that cannot be renewed retries later, uncounted', () async {
    final rig = _Rig();
    rig.store.put('notes', 'n1', {'title': 'a'});
    rig.transport.enqueueUpload(const Unauthorized());
    rig.transport.enqueueRefresh(SessionRefresh.rejected);
    await expectLater(
      rig.uploader.uploadNext(),
      throwsA(isA<SyncRetryLater>().having((e) => e.counted, 'counted', isFalse)),
    );
    expect(rig.transport.uploads, hasLength(1));
    expect(rig.store.queuedOps, 1);
  });

  test('a permanent failure refuses the whole chunk and completes', () async {
    final rig = _Rig();
    rig.store.transaction(() {
      rig.store.put('notes', 'a', {'title': 'a'});
      rig.store.put('notes', 'b', {'title': 'b'});
    });
    rig.transport.enqueueUpload(const Conflict('no'));
    final s = (await rig.uploader.uploadNext())!;
    expect(s.rejected, 2);
    expect(s.outcomes.every((o) => o.verdict.code == 'upload_rejected'), isTrue);
    expect(rig.store.queuedOps, 0);
    expect(await rig.store.rejections(), hasLength(2));
  });

  test('a rate_limited verdict is retried, never refused', () async {
    final rig = _Rig();
    rig.store.put('notes', 'n1', {'title': 'a'});
    rig.transport.enqueueUpload(_res([_r(0, 'rejected', code: 'rate_limited')]));
    await expectLater(rig.uploader.uploadNext(), throwsA(isA<SyncRetryLater>()));
    expect(rig.store.queuedOps, 1);
    expect(await rig.store.rejections(), isEmpty);
    await rig.uploader.uploadNext();
    expect(rig.store.queuedOps, 0);
  });

  test('an answer that skips an op is a counted retry', () async {
    final rig = _Rig();
    rig.store.put('notes', 'n1', {'title': 'a'});
    rig.transport.enqueueUpload(_res([]));
    await expectLater(
      rig.uploader.uploadNext(),
      throwsA(isA<SyncRetryLater>().having((e) => e.counted, 'counted', isTrue)),
    );
    expect(rig.store.meta.keys.single, startsWith('transient:'));
  });

  test('counted failures give the transaction up after the count and span', () async {
    final rig = _Rig(limits: const UploadLimits(transientMaxCount: 3, transientMaxSpan: Duration(minutes: 10)));
    rig.store.put('notes', 'n1', {'title': 'a'});
    for (var i = 0; i < 3; i++) {
      rig.transport.enqueueUpload(const Forbidden());
    }
    for (var i = 0; i < 2; i++) {
      await expectLater(rig.uploader.uploadNext(), throwsA(isA<SyncRetryLater>()));
      rig.t = rig.t.add(const Duration(minutes: 6));
    }
    rig.t = rig.t.add(const Duration(minutes: 1));
    final s = (await rig.uploader.uploadNext())!;
    expect(s.gaveUp, isTrue);
    expect(s.outcomes.single.verdict.code, 'server_error');
    expect(s.outcomes.single.sent, isFalse);
    expect(rig.store.queuedOps, 0);
    expect(rig.store.meta, isEmpty);
    expect((await rig.store.rejections()).single.code, 'server_error');
  });

  test('an idle count starts over', () async {
    final rig = _Rig(limits: const UploadLimits(transientMaxCount: 2, transientMaxSpan: Duration.zero));
    rig.store.put('notes', 'n1', {'title': 'a'});
    rig.transport.enqueueUpload(const Forbidden());
    rig.transport.enqueueUpload(const Forbidden());
    await expectLater(rig.uploader.uploadNext(), throwsA(isA<SyncRetryLater>()));
    rig.t = rig.t.add(const Duration(minutes: 11)); // past transientStale
    await expectLater(rig.uploader.uploadNext(), throwsA(isA<SyncRetryLater>()));
    expect(rig.store.queuedOps, 1);
  });

  test('5xx never counts however long it lasts', () async {
    final rig = _Rig(limits: const UploadLimits(transientMaxCount: 1, transientMaxSpan: Duration.zero));
    rig.store.put('notes', 'n1', {'title': 'a'});
    for (var i = 0; i < 4; i++) {
      rig.transport.enqueueUpload(const ServerError('down', statusCode: 503));
      await expectLater(rig.uploader.uploadNext(), throwsA(isA<SyncRetryLater>()));
    }
    expect(rig.store.queuedOps, 1);
    expect(await rig.store.rejections(), isEmpty);
  });

  test('an unsendable table and an empty patch are decided on the device', () async {
    final rig = _Rig(sendable: {'notes'});
    rig.store.transaction(() {
      rig.store.put('local_only', 'x', {'v': 1});
      rig.store.patch('notes', 'n1', {});
      rig.store.put('notes', 'n2', {'title': 'b'});
    });
    final s = (await rig.uploader.uploadNext())!;
    expect(s.outcomes.map((o) => o.verdict.code ?? o.verdict.status), ['unsupported', 'already', 'ok']);
    expect(s.outcomes.map((o) => o.sent), [false, false, true]);
    expect(rig.transport.uploads.single.ops.map((o) => o.id), ['n2']);
  });

  test('chunks keep verdicts across a retry', () async {
    final rig = _Rig(limits: const UploadLimits(chunkSize: 1));
    rig.store.transaction(() {
      rig.store.put('notes', 'a', {'title': 'a'});
      rig.store.put('notes', 'b', {'title': 'b'});
    });
    rig.transport.enqueueUpload((UploadRequest r) => FakeSyncTransport.okAll(r));
    rig.transport.enqueueUpload(const ServerError('down', statusCode: 503));
    await expectLater(rig.uploader.uploadNext(), throwsA(isA<SyncRetryLater>()));
    expect(rig.transport.uploads.map((r) => r.ops.length), [1, 1]);
    final s = (await rig.uploader.uploadNext())!;
    expect(s.ok, 2);
    // only the unanswered op went out again
    expect(rig.transport.uploads.map((r) => r.ops.single.id), ['a', 'b', 'b']);
  });

  test('uploadPending loops and reports a retry instead of throwing', () async {
    final rig = _Rig();
    rig.store.put('notes', 'a', {'title': 'a'});
    rig.store.put('notes', 'b', {'title': 'b'});
    rig.store.put('notes', 'c', {'title': 'c'});
    rig.transport.enqueueUpload((UploadRequest r) => FakeSyncTransport.okAll(r));
    rig.transport.enqueueUpload(const NetworkFailure(NetworkFailureKind.timeout, baseUrl: 'x'));
    final s = await rig.uploader.uploadPending();
    expect(s.batches, 1);
    expect(s.ok, 1);
    expect(s.retryLater, isNotNull);
    expect(rig.store.queuedOps, 2);
    final s2 = await rig.uploader.uploadPending();
    expect(s2.batches, 2);
    expect(s2.retryLater, isNull);
    expect(s2.outcomeFor(0)!.verdict.isOk, isTrue);
  });

  test('a rejected row can be fixed and resent', () async {
    final rig = _Rig(rules: const OutcomeRules(createPuts: {'notes': null}));
    rig.store.put('notes', 'n1', {'title': ''});
    rig.transport.enqueueUpload(_res([_r(0, 'rejected', code: 'invalid')]));
    await rig.uploader.uploadNext();
    final note = (await rig.store.rejections()).single;
    expect(await rig.store.resend(note), SyncResendResult.queued);
    expect(await rig.store.rejections(), isEmpty);
    final s = (await rig.uploader.uploadNext())!;
    expect(s.ok, 1);
  });

  test('a surprise from the store counts against the transaction', () async {
    final rig = _Rig();
    rig.store.put('notes', 'n1', {'title': 'a'});
    final bad = SyncUploader(
      store: _ThrowingStore(rig.store),
      transport: rig.transport,
      clock: rig.clock,
    );
    await expectLater(
      bad.uploadNext(),
      throwsA(isA<SyncRetryLater>().having((e) => e.counted, 'counted', isTrue)),
    );
  });
}

class _ThrowingStore extends FakeSyncStore {
  _ThrowingStore(this.inner);
  final FakeSyncStore inner;

  @override
  Future<SyncBatch?> nextBatch() => inner.nextBatch();

  @override
  Future<void> applyVerdicts(List<SyncUploadOp> ops, Map<int, SyncVerdict> verdicts, DateTime now) =>
      throw StateError('disk full');
}
