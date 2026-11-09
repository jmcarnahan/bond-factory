/// HTTP client of the task routes.
library;

import 'package:bond_api/bond_api.dart';
import 'package:bond_json/bond_json.dart';

import 'task.dart';
import 'task_draft.dart';
import 'task_filters.dart';

/// The task routes under [prefix]. Failures are the `bond_api` exceptions
/// (`NotFound` for `task_not_found`, `Forbidden` for `not_task_editor`,
/// `Conflict` for `id_taken`, `ValidationError`/`BadRequest` for a bad body).
class TasksApi {
  TasksApi(this.client, {this.prefix = '/tasks'});

  final ApiClient client;
  final String prefix;

  String _one(String id) => '$prefix/${Uri.encodeComponent(id)}';

  Future<TaskPage> list([TaskFilters filters = const TaskFilters()]) async =>
      TaskPage.fromJson(await client.getJson(prefix, query: filters.toQuery()));

  Future<TaskSummary> summary({String? today}) async =>
      TaskSummary.fromJson(await client.getJson('$prefix/summary', query: {'today': today}));

  Map<String, Object?>? _q(String? today) => today == null ? null : {'today': today};

  /// [today] (`YYYY-MM-DD`) is the client's today; the server computes
  /// `overdue` against it. It is optional on every call that returns a task.
  Future<Task> get(String id, {String? today}) async =>
      Task.fromJson(await client.getJson(_one(id), query: _q(today)));

  /// `POST` answering 201 with the new task.
  Future<Task> create(TaskDraft draft, {String? today}) async =>
      Task.fromJson(await client.postJson(prefix, body: draft.toJson(), query: _q(today)));

  /// `PUT` with only the fields present in [patch].
  Future<Task> update(String id, TaskPatch patch, {String? today}) async =>
      Task.fromJson(await client.putJson(_one(id), body: patch.toJson(), query: _q(today)));

  Future<Task> complete(String id, {String? today}) async =>
      Task.fromJson(await client.postJson('${_one(id)}/complete', query: _q(today)));

  Future<Task> reopen(String id, {String? today}) async =>
      Task.fromJson(await client.postJson('${_one(id)}/reopen', query: _q(today)));

  /// `DELETE` answering 204.
  Future<void> delete(String id) async {
    await client.deleteJson(_one(id));
  }

  /// Ticks one checklist line done or open.
  Future<Task> setChecklistItem(String id, String itemId, {required bool done}) async => Task.fromJson(
      await client.putJson('${_one(id)}/checklist/${Uri.encodeComponent(itemId)}', body: {'done': done}));
}

/// Routes that exist only in the fake-mode example server. Kept apart from
/// [TasksApi] so an app cannot call them by accident.
class DemoJobsApi {
  DemoJobsApi(this.client, {this.tickPath = '/jobs/tick', this.noticesPath = '/tasks/notices'});

  final ApiClient client;
  final String tickPath;
  final String noticesPath;

  /// Runs every job due as of [now] and returns the server's answer.
  Future<Map<String, Object?>> runDueJobs(DateTime now) =>
      client.postJson(tickPath, body: {'now': jiso(now)});

  /// The reminders the fake notifier has delivered. Accepts a bare list or
  /// `{items: [...]}`.
  Future<List<Map<String, Object?>>> notices() async {
    final v = await client.request('GET', noticesPath);
    final raw = v is Map ? v['items'] : v;
    return jlistOf(raw, jmapOf);
  }
}
