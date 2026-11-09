import 'dart:convert';
import 'dart:io';

import 'package:bond_api/bond_api.dart';
import 'package:bond_sync/bond_sync.dart';
import 'package:bond_sync/testing.dart';
import 'package:test/test.dart';

const _dir = '../../fixtures/sync';

Map<String, Object?> _load(String name) =>
    (jsonDecode(File('$_dir/$name').readAsStringSync()) as Map).cast<String, Object?>();

Object? _norm(Object? v) => jsonDecode(jsonEncode(v));

void main() {
  test('the fixture directory is where the contract says', () {
    expect(Directory(_dir).existsSync(), isTrue);
  });

  group('upload requests round trip', () {
    for (final name in [
      'upload_request_ok.json',
      'upload_request_mixed.json',
      'upload_request_too_many_ops.json',
      'upload_request_dup_seq.json',
    ]) {
      test(name, () {
        final j = _load(name);
        final r = UploadRequest.fromJson(j);
        // The client omits a null transaction_id; the server reads absent and null alike.
        final expected = {...j}..removeWhere((k, v) => k == 'transaction_id' && v == null);
        expect(_norm(r.toJson()), _norm(expected));
        expect(r.ops, isNotEmpty);
      });
    }

    test('null action is omitted, a null transaction id too', () {
      final r = UploadRequest.fromJson(_load('upload_request_dup_seq.json'));
      expect(r.transactionId, isNull);
      expect(r.toJson().containsKey('transaction_id'), isFalse);
      expect(r.ops.every((o) => !o.toJson().containsKey('action')), isTrue);
    });

    test('101 ops split into the contract maximum and one more', () {
      final r = UploadRequest.fromJson(_load('upload_request_too_many_ops.json'));
      expect(r.ops, hasLength(101));
      expect(chunkOps(r.ops, const UploadLimits()).map((c) => c.length), [100, 1]);
    });

    test('a delete carries an empty data object', () {
      final r = UploadRequest.fromJson(_load('upload_request_mixed.json'));
      final del = r.ops.firstWhere((o) => o.op == 'delete');
      expect(del.toJson()['data'], isEmpty);
    });
  });

  group('upload responses round trip', () {
    for (final name in ['upload_response_mixed.json', 'upload_response_all_codes.json']) {
      test(name, () {
        final j = _load(name)..remove('_note');
        expect(_norm(UploadResponse.fromJson(j).toJson()), _norm(j));
      });
    }

    test('every verdict code in the fixture has plain words', () {
      final r = UploadResponse.fromJson(_load('upload_response_all_codes.json'));
      for (final res in r.results) {
        final code = res.code;
        if (code != null) expect(kVerdictText[code], isNotNull, reason: code);
      }
      expect(r.results.firstWhere((e) => e.resolvedId != null).resolvedId, 'server-row-1');
      expect(r.serverNow, DateTime.utc(2026, 11, 8, 17, 4, 5, 123));
    });

    test('the mixed answer through the uploader', () async {
      final request = UploadRequest.fromJson(_load('upload_request_mixed.json'));
      final response = UploadResponse.fromJson(_load('upload_response_mixed.json'));
      final store = FakeSyncStore(rules: const OutcomeRules(createPuts: {'notes': null}));
      store.transaction(() {
        for (final o in request.ops) {
          switch (o.op) {
            case 'put':
              store.put(o.table, o.id, o.data);
            case 'patch':
              store.patch(o.table, o.id, o.data);
            default:
              store.delete(o.table, o.id);
          }
        }
      });
      final transport = FakeSyncTransport()..enqueueUpload(response);
      final uploader = SyncUploader(store: store, transport: transport, clock: ServerClock());
      final s = (await uploader.uploadNext())!;
      expect(s.ok, 2);
      expect(s.skipped, 1);
      expect(s.rejected, 5);
      // rejected puts leave no local row; the accepted one stays
      expect((await store.rows('notes')).map((r) => r['id']), ['note-1']);
      final notes = await store.rejections();
      expect(notes.map((n) => n.code).toSet(), {'invalid', 'conflict', 'not_found', 'unsupported'});
      expect(notes.firstWhere((n) => n.rowId == 'note-2').message, 'title_required');
    });
  });

  group('token', () {
    test('the token response parses', () {
      final f = _load('sync_token_claims.json');
      final j = {...(f['token_response']! as Map).cast<String, Object?>(), 'token': f['example_token']};
      final t = SyncToken.fromJson(j);
      expect(t.token.split('.'), hasLength(3));
      expect(t.endpoint, 'http://localhost:8095');
      expect(t.expiresAt, DateTime.utc(2026, 11, 8, 17, 15));
      expect(t.serverNow, DateTime.utc(2026, 11, 8, 17, 4, 5, 123));
      // expires_at agrees with server_now: a token minted at server_now is valid for the 15-minute window.
      expect(t.expiresAt.isAfter(t.serverNow!), isTrue);
      expect(t.expiresAt.difference(t.serverNow!), lessThanOrEqualTo(const Duration(minutes: 15)));
    });

    test('the sync_off body is a 503 the uploader retries without counting', () {
      final off = (_load('sync_token_claims.json')['off_response']! as Map).cast<String, Object?>();
      final e = ErrorBody.parse(off['status']! as int, off['body']);
      expect(e, isA<ServerError>().having((x) => x.code, 'code', 'sync_off'));
      expect(mapSyncFailure(e), SyncFailure.transientNoCount);
    });
  });

  test('new row ids satisfy the dispatcher id rule', () {
    final ids = _load('bad_ids.json');
    final rule = RegExp(r'^[A-Za-z0-9_-]{1,64}$');
    for (final id in (ids['ok']! as List).cast<String>()) {
      expect(rule.hasMatch(id), isTrue, reason: id);
    }
    for (final id in (ids['invalid']! as List).cast<String>()) {
      expect(rule.hasMatch(id), isFalse, reason: id);
    }
    for (var i = 0; i < 20; i++) {
      expect(rule.hasMatch(newId()), isTrue);
    }
  });
}
