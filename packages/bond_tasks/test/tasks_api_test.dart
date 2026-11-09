import 'dart:convert';
import 'dart:io';

import 'package:bond_api/bond_api.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:test/test.dart';

Map<String, Object?> _fixture() =>
    jsonDecode(File('../../fixtures/tasks/task.json').readAsStringSync()) as Map<String, Object?>;

class _Rig {
  _Rig(this.answer) {
    api = TasksApi(ApiClient(
      baseUrl: Uri.parse('https://api.test/v1'),
      http: MockClient((r) async {
        seen.add(r);
        return answer(r);
      }),
    ));
    demo = DemoJobsApi(ApiClient(
      baseUrl: Uri.parse('https://api.test/v1'),
      http: MockClient((r) async {
        seen.add(r);
        return answer(r);
      }),
    ));
  }

  final http.Response Function(http.Request) answer;
  final List<http.Request> seen = [];
  late final TasksApi api;
  late final DemoJobsApi demo;
}

http.Response _json(Object? body, [int status = 200]) =>
    http.Response(jsonEncode(body), status, headers: {'content-type': 'application/json'});

void main() {
  test('list sends the filter query and parses the envelope', () async {
    final r = _Rig((_) => _json({'items': [_fixture()], 'total': 1, 'limit': 50, 'offset': 0}));
    final page = await r.api.list(const TaskFilters(scope: 'mine', status: 'open', today: '2026-03-12'));
    expect(r.seen.single.method, 'GET');
    expect(r.seen.single.url.path, '/v1/tasks');
    expect(r.seen.single.url.queryParameters, {'scope': 'mine', 'status': 'open', 'today': '2026-03-12'});
    expect(page.items.single.id, 'task-0001');
    expect(page.total, 1);
  });

  test('summary hits /tasks/summary', () async {
    final r = _Rig((_) => _json({'open': 3, 'overdue': 1, 'due_today': 1, 'no_date': 0}));
    final s = await r.api.summary(today: '2026-03-12');
    expect(r.seen.single.url.path, '/v1/tasks/summary');
    expect(r.seen.single.url.queryParameters['today'], '2026-03-12');
    expect(s.overdue, 1);
  });

  test('get reads one task', () async {
    final r = _Rig((_) => _json(_fixture()));
    final t = await r.api.get('task-0001');
    expect(r.seen.single.url.path, '/v1/tasks/task-0001');
    expect(t.title, 'Send the signed estimate');
  });

  test('create POSTs the draft and accepts 201', () async {
    final r = _Rig((_) => _json(_fixture(), 201));
    final t = await r.api.create(const TaskDraft(title: 'Send the signed estimate'));
    expect(r.seen.single.method, 'POST');
    expect(r.seen.single.url.path, '/v1/tasks');
    expect((jsonDecode(r.seen.single.body) as Map)['title'], 'Send the signed estimate');
    expect(t.id, 'task-0001');
  });

  test('update PUTs a patch with an explicit null', () async {
    final r = _Rig((_) => _json(_fixture()));
    await r.api.update('task-0001', const TaskPatch(dueDate: Present(null)));
    expect(r.seen.single.method, 'PUT');
    final body = jsonDecode(r.seen.single.body) as Map;
    expect(body.containsKey('due_date'), isTrue);
    expect(body['due_date'], isNull);
    expect(body.containsKey('notes'), isFalse);
  });

  test('complete and reopen POST to their routes', () async {
    final r = _Rig((_) => _json(_fixture()));
    await r.api.complete('task-0001');
    await r.api.reopen('task-0001');
    expect(r.seen.map((q) => '${q.method} ${q.url.path}'), [
      'POST /v1/tasks/task-0001/complete',
      'POST /v1/tasks/task-0001/reopen',
    ]);
  });

  test('the client today rides along as a query on task calls', () async {
    final r = _Rig((_) => _json(_fixture()));
    await r.api.complete('task-0001', today: '2026-03-12');
    await r.api.create(const TaskDraft(title: 'T'), today: '2026-03-12');
    await r.api.get('task-0001');
    expect(r.seen[0].url.queryParameters, {'today': '2026-03-12'});
    expect(r.seen[1].url.queryParameters, {'today': '2026-03-12'});
    expect(r.seen[2].url.hasQuery, isFalse);
  });

  test('delete accepts 204 with no body', () async {
    final r = _Rig((_) => http.Response('', 204));
    await r.api.delete('task-0001');
    expect(r.seen.single.method, 'DELETE');
    expect(r.seen.single.url.path, '/v1/tasks/task-0001');
  });

  test('setChecklistItem PUTs done', () async {
    final r = _Rig((_) => _json(_fixture()));
    await r.api.setChecklistItem('task-0001', 'chk-2', done: true);
    expect(r.seen.single.method, 'PUT');
    expect(r.seen.single.url.path, '/v1/tasks/task-0001/checklist/chk-2');
    expect(jsonDecode(r.seen.single.body), {'done': true});
  });

  test('ids are path encoded', () async {
    final r = _Rig((_) => _json(_fixture()));
    await r.api.get('a b');
    expect(r.seen.single.url.path, '/v1/tasks/a%20b');
  });

  test('a custom prefix is used', () async {
    final seen = <String>[];
    final api = TasksApi(
      ApiClient(
        baseUrl: Uri.parse('https://api.test'),
        http: MockClient((q) async {
          seen.add(q.url.path);
          return _json(_fixture());
        }),
      ),
      prefix: '/work/items',
    );
    await api.get('x');
    expect(seen.single, '/work/items/x');
  });

  group('error mapping', () {
    test('404 task_not_found is NotFound with the code', () async {
      final r = _Rig((_) => _json({'detail': {'code': 'task_not_found', 'message': 'gone'}}, 404));
      await expectLater(
        r.api.get('x'),
        throwsA(isA<NotFound>().having((e) => e.code, 'code', 'task_not_found')),
      );
    });

    test('403 not_task_editor is Forbidden', () async {
      final r = _Rig((_) => _json({'detail': {'code': 'not_task_editor', 'message': 'no'}}, 403));
      await expectLater(r.api.complete('x'), throwsA(isA<Forbidden>()));
    });

    test('409 id_taken is Conflict', () async {
      final r = _Rig((_) => _json({'detail': {'code': 'id_taken', 'message': 'taken'}}, 409));
      await expectLater(r.api.create(const TaskDraft(title: 'T', id: 'a')), throwsA(isA<Conflict>()));
    });

    test('422 is a ValidationError', () async {
      final r = _Rig((_) => _json({'detail': {'code': 'validation_error', 'message': 'title: required'}}, 422));
      await expectLater(r.api.create(const TaskDraft(title: 'T')), throwsA(isA<ValidationError>()));
    });

    test('503 is a ServerError', () async {
      final r = _Rig((_) => _json({'detail': {'code': 'db_unavailable', 'message': 'down'}}, 503));
      await expectLater(r.api.list(), throwsA(isA<ServerError>()));
    });
  });

  group('DemoJobsApi', () {
    test('runDueJobs posts now as UTC ISO', () async {
      final r = _Rig((_) => _json({'ran': 1}));
      final out = await r.demo.runDueJobs(DateTime.utc(2026, 3, 12, 9, 17));
      expect(r.seen.single.url.path, '/v1/jobs/tick');
      expect(jsonDecode(r.seen.single.body), {'now': '2026-03-12T09:17:00.000Z'});
      expect(out['ran'], 1);
    });

    test('notices accepts a list or an items envelope', () async {
      final a = _Rig((_) => _json([{'task_id': 't1'}]));
      expect((await a.demo.notices()).single['task_id'], 't1');
      final b = _Rig((_) => _json({'items': [{'task_id': 't2'}]}));
      expect((await b.demo.notices()).single['task_id'], 't2');
      expect(b.seen.single.url.path, '/v1/tasks/notices');
    });
  });
}
