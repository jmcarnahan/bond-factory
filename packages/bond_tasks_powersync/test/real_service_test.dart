// Written, never run in this repo (it ships no sync stack). See docs/test/MOBILE.md, "The real-service sync lane".
//
// Opt-in: runs only through `make test-sync-service`, which sets the BOND_SYNC_* variables. The default suite skips it
// (the package Makefile and `make test-flutter` pass `--exclude-tags real_service`). It does a put, a patch, a complete and a refused write through the example
// service's upload route, for tasks and for notices, against a real PowerSync service and a real database.
//
// ignore_for_file: depend_on_referenced_packages
@Tags(['real_service'])
@TestOn('vm')
library;

import 'dart:convert';
import 'dart:io';

import 'package:bond_sync/bond_sync.dart';
import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_powersync/bond_tasks_powersync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:powersync/powersync.dart';

/// BOND_SYNC_API_URL      the example service, for example http://localhost:8012
/// BOND_SYNC_API_TOKEN    a session bearer token of a test user on that service
/// BOND_SYNC_SERVICE_URL  the PowerSync service (the example's /sync/token answer names it; this overrides it)
/// BOND_SYNC_POSTGRES_URL the database the service replicates from; the make target checks it is set, this test
///                        never connects to it (the service does)
String? _env(String name) {
  final v = Platform.environment[name];
  return v == null || v.isEmpty ? null : v;
}

class _HttpTransport implements SyncTransport {
  _HttpTransport(this.api, this.token);
  final String api;
  final String token;

  Future<Map<Object?, Object?>> _post(String path, Object? body) async {
    final client = HttpClient();
    try {
      final req = await client.postUrl(Uri.parse('$api$path'));
      req.headers
        ..set('authorization', 'Bearer $token')
        ..set('content-type', 'application/json');
      req.write(jsonEncode(body ?? <String, Object?>{}));
      final res = await req.close();
      final text = await res.transform(utf8.decoder).join();
      if (res.statusCode != 200) throw HttpException('$path answered ${res.statusCode}: $text');
      return (jsonDecode(text) as Map).cast<Object?, Object?>();
    } finally {
      client.close();
    }
  }

  @override
  Future<SyncToken> fetchToken() async => SyncToken.fromJson(await _post('/sync/token', null));

  @override
  Future<UploadResponse> upload(UploadRequest request) async =>
      UploadResponse.fromJson(await _post('/sync/upload', request.toJson()));

  @override
  Future<SessionRefresh> refreshSession() async => SessionRefresh.rejected;
}

final _noticeColumns = ['user_id', 'kind', 'title', 'body', 'data', 'created_at', 'read_at', 'dismissed_at'];

void main() {
  final api = _env('BOND_SYNC_API_URL');
  final bearer = _env('BOND_SYNC_API_TOKEN');
  final skip = (api == null || bearer == null) ? 'set BOND_SYNC_API_URL and BOND_SYNC_API_TOKEN (make test-sync-service)' : null;

  late Directory dir;
  late PowerSyncDatabase raw;
  late SyncDb db;
  late SyncConnector connector;
  late PowerSyncTaskRepository repo;
  final serverClock = ServerClock();

  Future<List<SyncRow>> rejections() => db.getAll('SELECT * FROM sync_rejections ORDER BY created_at');

  /// Uploads every queued transaction through the example's /sync/upload.
  Future<void> flush() async {
    for (var i = 0; i < 50; i++) {
      if (await db.nextCrudTransaction() == null) return;
      await connector.uploadData(raw);
    }
    fail('the upload queue did not drain');
  }

  setUp(() async {
    dir = Directory.systemTemp.createTempSync('btp_service');
    final policy = SyncPolicy(
      schema: Schema([...tasksTables(), Table('notices', [for (final c in _noticeColumns) Column.text(c)]), ...syncSupportTables()]),
      endpointOverride: _env('BOND_SYNC_SERVICE_URL'),
    );
    raw = PowerSyncDatabase(schema: policy.schema, path: '${dir.path}/t.db');
    await raw.initialize();
    db = PowerSyncDb(raw);
    connector = SyncConnector(transport: _HttpTransport(api!, bearer!), clock: serverClock, policy: policy);
    repo = PowerSyncTaskRepository(db, userId: 'set-by-session', clock: const TaskClock(DateTime.now));
  });

  tearDown(() async {
    await raw.close();
    dir.deleteSync(recursive: true);
  });

  test('tasks: put, patch, complete are accepted; a refused write is kept as a rejection', () async {
    final id = 'svc-${DateTime.now().microsecondsSinceEpoch}';
    await repo.create(TaskDraft(title: 'Round trip', id: id, dueDate: '2026-12-01'));
    await flush();
    await repo.update(id, const TaskPatch(title: 'Round trip, edited'));
    await flush();
    await repo.complete(id);
    await flush();
    expect(await rejections(), isEmpty, reason: 'put, patch and complete are all accepted');

    // A put with no title is refused by the server (`invalid`).
    await db.execute("INSERT INTO tasks (id, title, status, owner_user_id) VALUES (?, '', 'open', 'set-by-session')", ['$id-bad']);
    await flush();
    final refused = await rejections();
    expect(refused.where((r) => r['table_name'] == 'tasks' && r['row_id'] == '$id-bad'), isNotEmpty);
  }, skip: skip);

  test('notices: a put is refused (the server makes notices); a read patch on a synced notice is accepted', () async {
    final stamp = DateTime.now().toUtc().toIso8601String();
    await db.execute(
      "INSERT INTO notices (id, user_id, kind, title, created_at) VALUES (?, 'set-by-session', 'task_due', 'Client made', ?)",
      ['svc-notice-${DateTime.now().microsecondsSinceEpoch}', stamp],
    );
    await flush();
    expect((await rejections()).where((r) => r['table_name'] == 'notices'), isNotEmpty);

    // Needs a notice the server made for this user (the adopter seeds one, for example with a sweep) to arrive by sync.
    await raw.connect(connector: connector);
    await raw.waitForFirstSync();
    final seeded = await db.getAll("SELECT id FROM notices WHERE read_at IS NULL AND id NOT LIKE 'svc-notice-%' LIMIT 1");
    if (seeded.isEmpty) {
      markTestSkipped('no server-made notice synced down; seed one for the test user and run again');
      return;
    }
    final before = (await rejections()).length;
    await db.execute('UPDATE notices SET read_at = ? WHERE id = ?', [stamp, seeded.first['id']]);
    await flush();
    expect((await rejections()).length, before, reason: 'the read patch is accepted');
  }, skip: skip);
}
