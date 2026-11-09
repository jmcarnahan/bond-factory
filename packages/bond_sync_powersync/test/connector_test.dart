import 'package:bond_api/bond_api.dart';
import 'package:bond_sync/bond_sync.dart';
import 'package:bond_sync/testing.dart';
import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:powersync/powersync.dart';

final _schema = Schema([
  const Table('notes', [Column.text('title')]),
  const Table('device_only_sync', [Column.text('v')]),
  ...syncSupportTables(),
]);

SyncToken _token({String? endpoint = 'https://sync.example.com', DateTime? now}) => SyncToken(
      token: 'tok-1',
      expiresAt: DateTime.utc(2026, 11, 8, 12),
      endpoint: endpoint,
      serverNow: now,
    );

SyncConnector _connector(
  FakeSyncTransport transport, {
  SyncPolicy? policy,
  void Function(DateTime)? onNow,
  ServerClock? clock,
}) =>
    SyncConnector(
      transport: transport,
      clock: clock ?? ServerClock(() => DateTime.utc(2026, 11, 8, 10)),
      policy: policy ?? SyncPolicy(schema: _schema, notUploadedTables: const {'device_only_sync'}),
      onServerNow: onNow,
    );

void main() {
  group('fetchCredentials', () {
    test('turns the token into credentials and notes the server clock', () async {
      final t = FakeSyncTransport()..enqueueToken(_token(now: DateTime.utc(2026, 11, 8, 10, 0, 20)));
      DateTime? told;
      final clock = ServerClock(() => DateTime.utc(2026, 11, 8, 10));
      final c = await _connector(t, onNow: (d) => told = d, clock: clock).fetchCredentials();
      expect(c!.endpoint, 'https://sync.example.com');
      expect(c.token, 'tok-1');
      expect(c.expiresAt, DateTime.utc(2026, 11, 8, 12));
      expect(clock.skew, const Duration(seconds: 20));
      expect(told, DateTime.utc(2026, 11, 8, 10, 0, 20));
    });

    test('a 401 renews the session and asks once more', () async {
      final t = FakeSyncTransport()
        ..enqueueToken(const Unauthorized())
        ..enqueueToken(_token());
      final c = await _connector(t).fetchCredentials();
      expect(c!.token, 'tok-1');
      expect(t.tokenCalls, 2);
      expect(t.refreshCalls, 1);
    });

    test('a 401 that cannot be renewed is rethrown without a second ask', () async {
      final t = FakeSyncTransport()
        ..enqueueToken(const Unauthorized())
        ..enqueueRefresh(SessionRefresh.rejected);
      await expectLater(_connector(t).fetchCredentials(), throwsA(isA<Unauthorized>()));
      expect(t.tokenCalls, 1);
    });

    test('a second 401 after renewal is not retried again', () async {
      final t = FakeSyncTransport()
        ..enqueueToken(const Unauthorized())
        ..enqueueToken(const Unauthorized());
      await expectLater(_connector(t).fetchCredentials(), throwsA(isA<Unauthorized>()));
      expect(t.tokenCalls, 2);
      expect(t.refreshCalls, 1);
    });

    test('another failure is rethrown and never renews', () async {
      final t = FakeSyncTransport()..enqueueToken(const ServerError('sync_off', statusCode: 503));
      await expectLater(_connector(t).fetchCredentials(), throwsA(isA<ServerError>()));
      expect(t.refreshCalls, 0);
    });

    test('no endpoint is a StateError; the override wins', () async {
      final none = FakeSyncTransport()..enqueueToken(_token(endpoint: null));
      await expectLater(_connector(none).fetchCredentials(), throwsStateError);
      final empty = FakeSyncTransport()..enqueueToken(_token(endpoint: ''));
      await expectLater(_connector(empty).fetchCredentials(), throwsStateError);
      final over = FakeSyncTransport()..enqueueToken(_token(endpoint: null));
      final c = await _connector(over, policy: SyncPolicy(schema: _schema, endpointOverride: 'http://localhost:8095'))
          .fetchCredentials();
      expect(c!.endpoint, 'http://localhost:8095');
    });
  });

  group('uploadWith', () {
    test('an empty queue returns quietly', () async {
      final t = FakeSyncTransport();
      await _connector(t).uploadWith(FakeSyncStore());
      expect(t.uploads, isEmpty);
    });

    test('accepted writes complete', () async {
      final store = FakeSyncStore()..put('notes', 'n1', {'title': 'a'});
      final t = FakeSyncTransport();
      await _connector(t).uploadWith(store);
      expect(store.queuedOps, 0);
      expect(t.uploads.single.ops.single.id, 'n1');
    });

    test('a permanent refusal completes without throwing', () async {
      final store = FakeSyncStore()..put('notes', 'n1', {'title': 'a'});
      final t = FakeSyncTransport()..enqueueUpload(const Conflict('x'));
      await _connector(t).uploadWith(store);
      expect(store.queuedOps, 0);
      expect((await store.rejections()).single.code, 'upload_rejected');
    });

    test('every retry reaches the SDK as a plain Exception', () async {
      for (final error in <Object>[
        const NetworkFailure(NetworkFailureKind.noAnswer, baseUrl: 'x'),
        const ServerError('down', statusCode: 503),
        const Forbidden(),
        const Unauthorized(),
      ]) {
        final store = FakeSyncStore()..put('notes', 'n1', {'title': 'a'});
        final t = FakeSyncTransport()
          ..enqueueUpload(error)
          ..enqueueRefresh(SessionRefresh.rejected);
        await expectLater(
          _connector(t).uploadWith(store),
          throwsA(isA<Exception>().having((e) => e is SyncRetryLater, 'is SyncRetryLater', isFalse)),
          reason: '$error',
        );
        expect(store.queuedOps, 1, reason: '$error');
      }
    });

    test('a store that blows up is a retry, not a crash', () async {
      await expectLater(_connector(FakeSyncTransport()).uploadWith(_BrokenStore()), throwsA(isA<Exception>()));
    });

    test('tables that are not uploaded get an unsupported verdict and are never sent', () async {
      final store = FakeSyncStore();
      store.transaction(() {
        store.put('device_only_sync', 'x', {'v': '1'});
        store.put('notes', 'n1', {'title': 'a'});
      });
      final t = FakeSyncTransport();
      await _connector(t).uploadWith(store);
      expect(t.uploads.single.ops.map((o) => o.table), ['notes']);
      expect(store.queuedOps, 0);
      expect((await store.rejections()).single.code, 'unsupported');
    });
  });
}

class _BrokenStore extends FakeSyncStore {
  @override
  Future<SyncBatch?> nextBatch() => throw StateError('disk gone');
}
