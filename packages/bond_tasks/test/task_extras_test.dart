import 'dart:convert';
import 'dart:io';

import 'package:bond_api/bond_api.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:test/test.dart';

Map<String, Object?> _fixture() =>
    jsonDecode(File('../../fixtures/tasks/task.json').readAsStringSync()) as Map<String, Object?>;

void main() {
  test('task_extras_json: unknown keys land in extras, toJson stays exact', () {
    final json = _fixture();
    final plain = Task.fromJson(json);
    expect(plain.extras, isEmpty);
    final t = Task.fromJson({...json, 'loan_id': 'L1', 'rank': 3});
    expect(t.extras, {'loan_id': 'L1', 'rank': 3});
    expect(t.toJson(), plain.toJson());
    expect(t.toJson().containsKey('loan_id'), isFalse);
    expect(t.copyWith(status: TaskStatus.done).extras, {'loan_id': 'L1', 'rank': 3});
  });

  test('draft_extras_merge: extras follow the known keys and never override one', () {
    final j = const TaskDraft(title: 'T', extras: {'loan_id': 'L1', 'title': 'evil', 'checklist': 5}).toJson();
    expect(j['loan_id'], 'L1');
    expect(j['title'], 'T');
    expect(j['checklist'], isEmpty);
    expect(const TaskDraft(title: 'T').toJson().containsKey('loan_id'), isFalse);

    final p = const TaskPatch(title: 'N', extras: {'loan_id': null, 'title': 'evil'}).toJson();
    expect(p, {'title': 'N', 'loan_id': null});
    expect(const TaskPatch().toJson(), isEmpty);
    expect(TaskPatch.fromDraft(const TaskDraft(title: 'T', extras: {'loan_id': 'L1'})).toJson()['loan_id'], 'L1');
  });

  test('tasks_api_posts_extras: create and update send the extras', () async {
    final seen = <http.Request>[];
    final api = TasksApi(ApiClient(
      baseUrl: Uri.parse('https://api.test/v1'),
      http: MockClient((r) async {
        seen.add(r);
        return http.Response(jsonEncode({..._fixture(), 'loan_id': 'L1'}), 200,
            headers: {'content-type': 'application/json'});
      }),
    ));
    final t = await api.create(const TaskDraft(title: 'T', extras: {'loan_id': 'L1'}));
    await api.update('task-0001', const TaskPatch(extras: {'loan_id': 'L2'}));
    expect((jsonDecode(seen[0].body) as Map)['loan_id'], 'L1');
    expect(jsonDecode(seen[1].body), {'loan_id': 'L2'});
    expect(t.extras, {'loan_id': 'L1'});
  });
}
