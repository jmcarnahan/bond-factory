import 'package:bond_api/bond_api.dart';
import 'package:bond_sync/bond_sync.dart';
import 'package:bond_sync/testing.dart';
import 'package:bond_test_support/bond_test_support.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sdk_demo/src/example_api.dart';
import 'package:sdk_demo/src/pages/sync_page.dart';

Finder byId(String id) => find.byWidgetPredicate((w) => w is Semantics && w.properties.identifier == id);

String textOf(WidgetTester t, String id) =>
    t.widget<Text>(find.descendant(of: byId(id), matching: find.byType(Text))).data!;

Future<void> tapLabel(WidgetTester t, String label) async {
  await t.tap(find.text(label));
  await t.pump();
}

Future<void> settle(WidgetTester t) async {
  for (var i = 0; i < 5; i++) {
    await t.pump(const Duration(milliseconds: 20));
  }
}

/// Refuses every op whose title is empty, accepts the rest.
UploadResponse Function(UploadRequest) serverRule({DateTime? now}) => (r) => UploadResponse(
      serverNow: now,
      results: [
        for (final o in r.ops)
          o.data['title'] == ''
              ? SyncOpResult(seq: o.seq, status: 'rejected', code: 'invalid', message: 'title_required')
              : SyncOpResult(seq: o.seq, status: 'ok'),
      ],
    );

Future<void> pumpFake(WidgetTester t, FakeSyncTransport transport) async {
  setWideScreen(t, size: const Size(600, 2600));
  await pumpApp(t, SyncPage(transport: transport, ensureSignedIn: () async => null));
}

void main() {
  testWidgets('add row and add bad row queue writes and list the rows', (t) async {
    await pumpFake(t, FakeSyncTransport());
    expect(find.text('No rows yet. Add one.'), findsOneWidget);
    await tapLabel(t, 'Add row');
    await tapLabel(t, 'Add bad row');
    await settle(t);
    expect(find.text('Note 1'), findsOneWidget);
    expect(find.text('(no title)'), findsOneWidget);
    expect(find.text('Waiting to be sent'), findsNWidgets(2));
    expect(textOf(t, 'sdk.sync.queued'), 'Queued writes: 2');
    await expectNoOverlays(t);
  });

  testWidgets('upload shows one verdict per row, the refused one with code and text', (t) async {
    final transport = FakeSyncTransport()..enqueueUpload(serverRule());
    await pumpFake(t, transport);
    await tapLabel(t, 'Add row');
    await tapLabel(t, 'Add bad row');
    await tapLabel(t, 'Upload');
    await pumpUntil(t, find.textContaining('Sent 2'));

    expect(transport.uploads.single.ops.map((o) => o.toJson()['table']), ['notes', 'notes']);
    expect(transport.uploads.single.ops.last.data['title'], '');
    expect(textOf(t, 'sdk.sync.verdict-0'), 'ok');
    final bad = textOf(t, 'sdk.sync.verdict-1');
    expect(bad, contains('rejected: invalid'));
    expect(bad, contains(kVerdictText['invalid']!));
    expect(bad, contains('title_required'));
    expect(textOf(t, 'sdk.sync.queued'), 'Queued writes: 0');
    expect(find.textContaining('1 accepted, 1 refused'), findsOneWidget);
    await expectNoOverlays(t);
  });

  testWidgets('fix row then send again gets the row accepted', (t) async {
    final transport = FakeSyncTransport()
      ..enqueueUpload(serverRule())
      ..enqueueUpload(serverRule());
    await pumpFake(t, transport);

    OutlinedButton fixButton() => t.widget<OutlinedButton>(find.widgetWithText(OutlinedButton, 'Fix row'));
    await tapLabel(t, 'Add bad row');
    expect(fixButton().onPressed, isNull); // nothing refused yet

    await tapLabel(t, 'Upload');
    await pumpUntil(t, find.textContaining('rejected: invalid'));
    expect(fixButton().onPressed, isNotNull);

    await tapLabel(t, 'Fix row');
    await settle(t);
    expect(find.text('Fixed title'), findsOneWidget);
    expect(textOf(t, 'sdk.sync.queued'), 'Queued writes: 1');

    await tapLabel(t, 'Send again');
    await pumpUntil(t, find.textContaining('1 accepted, 0 refused'));
    expect(textOf(t, 'sdk.sync.verdict-0'), 'ok');
    expect(transport.uploads.last.ops.single.data['title'], 'Fixed title');
    expect(transport.uploads.last.ops.single.op, 'put');
    expect(fixButton().onPressed, isNull);
    await expectNoOverlays(t);
  });

  testWidgets('walked texts expose their visible text as the semantics label', (t) async {
    final transport = FakeSyncTransport()..enqueueUpload(serverRule(now: DateTime.utc(2026, 11, 8, 17, 4, 5, 123)));
    await pumpFake(t, transport);
    await tapLabel(t, 'Add bad row');
    await tapLabel(t, 'Upload');
    await pumpUntil(t, find.textContaining('Sent 1'));

    String labelOf(String id) => t.widget<Semantics>(byId(id)).properties.label!;
    for (final id in ['sdk.sync.queued', 'sdk.sync.info', 'sdk.sync.server-clock', 'sdk.sync.verdict-0']) {
      expect(labelOf(id), textOf(t, id), reason: id);
      expect(t.widget<Semantics>(byId(id)).excludeSemantics, isTrue, reason: id);
    }
    expect(labelOf('sdk.sync.verdict-0'), contains('rejected: invalid'));
  });

  testWidgets('adjacent verdicts are separate semantics nodes, each with its own label', (t) async {
    final handle = t.ensureSemantics();
    final transport = FakeSyncTransport()..enqueueUpload(serverRule());
    await pumpFake(t, transport);
    await tapLabel(t, 'Add row');
    await tapLabel(t, 'Add bad row');
    await tapLabel(t, 'Upload');
    await pumpUntil(t, find.textContaining('Sent 2'));

    for (final id in ['sdk.sync.verdict-0', 'sdk.sync.verdict-1']) {
      expect(t.widget<Semantics>(byId(id)).container, isTrue, reason: id);
    }
    final ok = t.getSemantics(byId('sdk.sync.verdict-0'));
    final bad = t.getSemantics(byId('sdk.sync.verdict-1'));
    expect(ok.id, isNot(bad.id));
    expect(ok.label, 'ok');
    expect(bad.label, contains('rejected: invalid'));
    expect(ok.label, isNot(contains('rejected')));
    handle.dispose();
  });

  testWidgets('the server clock shows server_now and the skew after an upload', (t) async {
    final now = DateTime.utc(2026, 11, 8, 17, 4, 5, 123);
    final transport = FakeSyncTransport()..enqueueUpload(serverRule(now: now));
    await pumpFake(t, transport);
    expect(textOf(t, 'sdk.sync.server-clock'), 'Server clock: not known yet');
    await tapLabel(t, 'Add row');
    await tapLabel(t, 'Upload');
    await pumpUntil(t, find.textContaining('Sent 1'));
    final text = textOf(t, 'sdk.sync.server-clock');
    expect(text, contains('server_now 2026-11-08T17:04:05.123Z'));
    expect(text, matches(RegExp(r'skew [+-]?\d+ ms \(server minus device\)')));
  });

  testWidgets('offline: the upload stops early and the writes stay queued', (t) async {
    final transport = FakeSyncTransport()
      ..enqueueUpload(const NetworkFailure(NetworkFailureKind.noAnswer, baseUrl: 'http://x'));
    await pumpFake(t, transport);
    await tapLabel(t, 'Add row');
    await tapLabel(t, 'Upload');
    await pumpUntil(t, find.textContaining('Stopped early'));
    expect(textOf(t, 'sdk.sync.queued'), 'Queued writes: 1');
    expect(find.text('Waiting to be sent'), findsOneWidget);
    await expectNoOverlays(t);
  });

  testWidgets('upload with nothing queued says so', (t) async {
    final transport = FakeSyncTransport();
    await pumpFake(t, transport);
    await tapLabel(t, 'Upload');
    await pumpUntil(t, find.text('Nothing was waiting.'));
    expect(transport.uploads, isEmpty);
  });

  group('over the shared client', () {
    Map<String, Object?> session() => {
          'token': 'sess-abc123',
          'user': {'id': 'demo-user-1', 'email': 'demo@example.com', 'name': 'Demo User', 'capabilities': <String>[]},
        };

    Future<CannedHttpClient> pumpLive(WidgetTester t, CannedResponses r) async {
      final http = CannedHttpClient(r);
      DemoSession.reset(client: http, base: Uri.parse('http://test.invalid'));
      addTearDown(DemoSession.reset);
      setWideScreen(t, size: const Size(600, 2600));
      await pumpApp(t, const SyncPage());
      return http;
    }

    testWidgets('upload signs in, posts the envelope to /sync/upload and shows the verdict', (t) async {
      final r = CannedResponses()
        ..json('POST', '/auth/demo', session())
        ..json('POST', '/sync/upload', {
          'results': [
            {'seq': 0, 'status': 'rejected', 'code': 'invalid', 'message': 'title_required'},
          ],
          'server_now': '2026-11-08T17:04:05.123Z',
        });
      final http = await pumpLive(t, r);
      await tapLabel(t, 'Add bad row');
      await tapLabel(t, 'Upload');
      await pumpUntil(t, find.textContaining('rejected: invalid'));

      expect(http.requestsTo('POST', '/auth/demo'), hasLength(1));
      final sent = http.requestsTo('POST', '/sync/upload').single;
      expect(sent.headers['Authorization'], 'Bearer sess-abc123');
      final body = sent.json! as Map;
      expect(body.containsKey('transaction_id'), isTrue);
      final op = (body['ops'] as List).single as Map;
      expect(op['table'], 'notes');
      expect(op['op'], 'put');
      expect((op['data'] as Map)['title'], '');
      expect(op.containsKey('action'), isFalse);
      await expectNoOverlays(t);
    });

    testWidgets('fetch token shows the tail, expiry and endpoint', (t) async {
      final r = CannedResponses()
        ..json('POST', '/auth/demo', session())
        ..json('POST', '/sync/token', {
          'token': 'a.b.zz9876',
          'expires_at': '2026-11-08T17:15:00Z',
          'endpoint': 'http://localhost:8095',
          'server_now': '2026-11-08T17:04:05.123Z',
        });
      final http = await pumpLive(t, r);
      await tapLabel(t, 'Fetch token');
      await pumpUntil(t, byId('sdk.sync.token'));

      expect(
        textOf(t, 'sdk.sync.token'),
        'Token ends zz9876 | expires_at 2026-11-08T17:15:00.000Z | endpoint http://localhost:8095',
      );
      expect(http.requestsTo('POST', '/sync/token').single.headers['Authorization'], 'Bearer sess-abc123');
      expect(textOf(t, 'sdk.sync.server-clock'), contains('server_now 2026-11-08T17:04:05.123Z'));
    });

    testWidgets('sync switched off shows the server code inline', (t) async {
      final r = CannedResponses()
        ..json('POST', '/auth/demo', session())
        ..json('POST', '/sync/token', {'detail': {'code': 'sync_off', 'message': 'Sync is not set up'}}, status: 503);
      await pumpLive(t, r);
      await tapLabel(t, 'Fetch token');
      await pumpUntil(t, byId('sdk.sync.error'));
      expect(textOf(t, 'sdk.sync.error'), 'code: sync_off | message: Sync is not set up');
      expect(byId('sdk.sync.token'), findsNothing);
      await expectNoOverlays(t);
    });
  });
}
