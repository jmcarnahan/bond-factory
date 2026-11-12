import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:bond_api/bond_api.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:test/test.dart';

Map<String, Object?> _fixture() =>
    jsonDecode(File('../../fixtures/tasks/task.json').readAsStringSync()) as Map<String, Object?>;

http.Response _json(Object? body, [int status = 200]) =>
    http.Response(jsonEncode(body), status, headers: {'content-type': 'application/json'});

class _Rig {
  _Rig({this.openItems = 1, this.fail = false}) {
    repo = RemoteTaskRepository(
      TasksApi(ApiClient(baseUrl: Uri.parse('https://api.test/v1'), http: MockClient(_answer))),
      clock: TaskClock(() => DateTime(2026, 3, 12, 10)),
      timeZone: () => 'America/Los_Angeles',
    );
  }

  int openItems;
  bool fail;
  final List<http.Request> seen = [];
  late final RemoteTaskRepository repo;

  Future<http.Response> _answer(http.Request r) async {
    seen.add(r);
    if (fail && r.method == 'GET') return _json({'error': 'boom'}, 500);
    if (r.method == 'GET' && r.url.path == '/v1/tasks') {
      return _json({'items': List.filled(openItems, _fixture()), 'total': openItems});
    }
    if (r.method == 'GET' && r.url.path == '/v1/tasks/today') return _json({'overdue': [], 'today': [], 'undated': []});
    if (r.method == 'GET') return _json({'open': 2, 'overdue': 0, 'due_today': 1, 'no_date': 0});
    if (r.method == 'DELETE') return http.Response('', 204);
    return _json(_fixture(), r.method == 'POST' && r.url.path == '/v1/tasks' ? 201 : 200);
  }

  http.Request get last => seen.last;
  Map<String, Object?> bodyOf(http.Request r) => jsonDecode(r.body) as Map<String, Object?>;
}

Future<void> _settle() => Future<void>.delayed(const Duration(milliseconds: 20));

void main() {
  test('with a zone, reads send the zone and no date', () async {
    final r = _Rig();
    await r.repo.list(const TaskFilters(scope: 'mine', status: 'open'));
    expect(r.last.url.queryParameters, {
      'scope': 'mine',
      'status': 'open',
      'time_zone': 'America/Los_Angeles',
    });
    await r.repo.today();
    expect(r.last.url.path, '/v1/tasks/today');
    expect(r.last.url.queryParameters, {'time_zone': 'America/Los_Angeles'});
    await r.repo.summary();
    expect(r.last.url.queryParameters, {'time_zone': 'America/Los_Angeles'});
  });

  test('a filter that names its own today or zone keeps it', () async {
    final r = _Rig();
    await r.repo.list(const TaskFilters(today: '2026-01-01', timeZone: 'UTC'));
    expect(r.last.url.queryParameters, {'today': '2026-01-01', 'time_zone': 'UTC'});
  });

  test('no timeZone callback sends the device date and no time_zone', () async {
    final repo = RemoteTaskRepository(TasksApi(ApiClient(
      baseUrl: Uri.parse('https://api.test/v1'),
      http: MockClient((req) async {
        expect(req.url.queryParameters.keys.toSet(), {'today'}, reason: 'no zone: the device date is sent');
        return _json({'open': 0});
      }),
    )));
    await repo.summary();
  });

  test('a timed draft carries due_at with Z; a date-only draft carries none', () async {
    final r = _Rig();
    await r.repo.create(const TaskDraft(title: 'a', dueDate: '2026-03-12', dueTime: '09:30'));
    final post = r.seen.firstWhere((x) => x.method == 'POST');
    final body = r.bodyOf(post);
    expect(DateTime.parse(body['due_at']! as String), DateTime(2026, 3, 12, 9, 30).toUtc());
    expect((body['due_at']! as String).endsWith('Z'), isTrue);
    expect(body['time_zone'], 'America/Los_Angeles');
    expect(post.url.queryParameters.containsKey('today'), isFalse);

    final r2 = _Rig();
    await r2.repo.create(const TaskDraft(title: 'b', dueDate: '2026-03-12'));
    expect(r2.bodyOf(r2.seen.firstWhere((x) => x.method == 'POST')).containsKey('due_at'), isFalse);
  });

  test('a draft due_at the caller set for a date-only task is not sent', () async {
    final r = _Rig();
    await r.repo.create(TaskDraft(title: 'b', dueDate: '2026-03-12', dueAt: DateTime.utc(2026, 3, 12, 5)));
    expect(r.bodyOf(r.seen.firstWhere((x) => x.method == 'POST')).containsKey('due_at'), isFalse);
  });

  test('update sends due_at only when the patch sets a date and a time', () async {
    final r = _Rig();
    await r.repo.update('t1', const TaskPatch(dueDate: Present('2026-03-12'), dueTime: Present('09:30')));
    final put = r.seen.firstWhere((x) => x.method == 'PUT');
    expect(r.bodyOf(put)['due_at'], isA<String>());
    expect(put.url.queryParameters['time_zone'], 'America/Los_Angeles');

    final r2 = _Rig();
    await r2.repo.update('t1', const TaskPatch(dueTime: Present(null)));
    expect(r2.bodyOf(r2.seen.firstWhere((x) => x.method == 'PUT')).containsKey('due_at'), isFalse);
  });

  test('the first listener gets the open list without a refresh; later reads emit too', () async {
    final r = _Rig(openItems: 2);
    final got = <int>[];
    final sub = r.repo.watchOpen().listen((l) => got.add(l.length));
    await _settle();
    expect(got, [2], reason: 'one initial read for the first listener');
    expect(r.seen.where((x) => x.method == 'GET'), hasLength(1));
    await r.repo.refresh();
    await _settle();
    expect(got, [2, 2]);
    r.openItems = 3;
    await r.repo.complete('task-0001');
    await _settle();
    expect(got, [2, 2, 3]);
    await r.repo.delete('task-0001');
    await _settle();
    expect(got.length, 4);
    await sub.cancel();
  });

  test('a second listener does not trigger another initial read', () async {
    final r = _Rig();
    final s1 = r.repo.watchOpen().listen((_) {});
    await _settle();
    final s2 = r.repo.watchOpen().listen((_) {});
    await _settle();
    expect(r.seen.where((x) => x.method == 'GET'), hasLength(1));
    await s1.cancel();
    await s2.cancel();
  });

  test('an older, slower re-read cannot emit after a newer one', () async {
    final gates = <int, Completer<void>>{};
    var reads = 0;
    final repo = RemoteTaskRepository(TasksApi(ApiClient(
      baseUrl: Uri.parse('https://api.test/v1'),
      http: MockClient((req) async {
        if (req.method == 'GET') {
          final n = ++reads;
          final gate = gates[n];
          if (gate != null) await gate.future;
          // read 1 (initial) and read 2 (slow, started first) see two tasks; read 3 (newer) sees one.
          final count = n == 3 ? 1 : 2;
          return _json({'items': List.filled(count, _fixture()), 'total': count});
        }
        return _json(_fixture());
      }),
    )));
    final got = <int>[];
    final sub = repo.watchOpen().listen((l) => got.add(l.length));
    await _settle();
    expect(got, [2]);
    gates[2] = Completer<void>();
    final first = repo.complete('task-0001'); // its re-read (read 2) is slow
    await _settle();
    final second = repo.complete('task-0002'); // its re-read (read 3) is fast and newer
    await second;
    await _settle();
    expect(got, [2, 1]);
    gates[2]!.complete(); // the stale read now finishes
    await first;
    await _settle();
    expect(got, [2, 1], reason: 'the stale list with the completed task must not be emitted');
    await sub.cancel();
  });

  test('open tasks are read from every page', () async {
    var calls = 0;
    final repo = RemoteTaskRepository(TasksApi(ApiClient(
      baseUrl: Uri.parse('https://api.test/v1'),
      http: MockClient((req) async {
        calls++;
        final offset = int.parse(req.url.queryParameters['offset']!);
        final n = offset == 0 ? 200 : 5;
        return _json({'items': List.filled(n, _fixture()), 'total': 205});
      }),
    )));
    final got = <int>[];
    final sub = repo.watchOpen().listen((l) => got.add(l.length));
    await _settle();
    expect(got, [205]);
    expect(calls, 2);
    await repo.refresh();
    await _settle();
    expect(got, [205, 205]);
    await sub.cancel();
  });

  test('a failed re-read goes to the stream as an error', () async {
    final r = _Rig(fail: true);
    final errors = <Object>[];
    final sub = r.repo.watchOpen().listen((_) {}, onError: errors.add);
    await _settle();
    expect(errors, hasLength(1), reason: 'the initial read failed');
    await expectLater(r.repo.refresh(), throwsA(isA<ApiException>()));
    await _settle();
    expect(errors, hasLength(2));
    // A write still succeeds; its re-read failure only reaches the stream.
    await r.repo.complete('task-0001');
    await _settle();
    expect(errors, hasLength(3));
    await sub.cancel();
  });

  test('dispose closes the stream', () async {
    final r = _Rig();
    final done = Completer<void>();
    r.repo.watchOpen().listen((_) {}, onDone: done.complete);
    r.repo.dispose();
    await done.future.timeout(const Duration(seconds: 1));
    await r.repo.refresh(); // no throw, no emit after dispose
  });
}
