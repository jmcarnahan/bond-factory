/// HTTP client of the task routes.
library;

import 'package:bond_api/bond_api.dart';
import 'package:bond_json/bond_json.dart';

import 'task.dart';
import 'task_draft.dart';
import 'task_candidates.dart';
import 'task_filters.dart';
import 'task_today.dart';

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

  Future<TaskSummary> summary({String? today, String? timeZone}) async =>
      TaskSummary.fromJson(await client.getJson('$prefix/summary', query: {'today': today, 'time_zone': timeZone}));

  Map<String, Object?>? _q(String? today, [String? timeZone]) => today == null && timeZone == null
      ? null
      : {'today': ?today, 'time_zone': ?timeZone};

  /// [today] (`YYYY-MM-DD`) is the client's today and [timeZone] the viewer's IANA zone; the server
  /// computes `overdue` against them. Both are optional on every call that returns a task.
  Future<Task> get(String id, {String? today, String? timeZone}) async =>
      Task.fromJson(await client.getJson(_one(id), query: _q(today, timeZone)));

  /// `POST` answering 201 with the new task.
  Future<Task> create(TaskDraft draft, {String? today, String? timeZone}) async =>
      Task.fromJson(await client.postJson(prefix, body: draft.toJson(), query: _q(today, timeZone)));

  /// `PUT` with only the fields present in [patch].
  Future<Task> update(String id, TaskPatch patch, {String? today, String? timeZone}) async =>
      Task.fromJson(await client.putJson(_one(id), body: patch.toJson(), query: _q(today, timeZone)));

  Future<Task> complete(String id, {String? today, String? timeZone}) async =>
      Task.fromJson(await client.postJson('${_one(id)}/complete', query: _q(today, timeZone)));

  Future<Task> reopen(String id, {String? today, String? timeZone}) async =>
      Task.fromJson(await client.postJson('${_one(id)}/reopen', query: _q(today, timeZone)));

  Future<Task> cancel(String id, {String? today, String? timeZone}) async =>
      Task.fromJson(await client.postJson('${_one(id)}/cancel', query: _q(today, timeZone)));

  /// `GET /tasks/today`: overdue, today, undated and done-today sections.
  Future<TaskToday> today({String? timeZone, String? today}) async =>
      TaskToday.fromJson(await client.getJson('$prefix/today', query: _q(today, timeZone)));

  /// `POST /tasks/parse`: finds tasks and events in [text]; creates nothing. 429 is `capture_denied`.
  Future<ParseResult> parse(String text, {String? today, String? timeZone}) async =>
      ParseResult.fromJson(await client.postJson('$prefix/parse', body: {
        'text': text,
        'today': ?today,
        'time_zone': ?timeZone,
      }));

  /// `GET /tasks/links/search`.
  Future<List<TaskLink>> searchLinks(String kind, String query) async => jlist(
      await client.getJson('$prefix/links/search', query: {'kind': kind, 'q': query}), 'items', TaskLink.fromJson);

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
  DemoJobsApi(this.client, {this.tickPath = '/jobs/tick'});

  final ApiClient client;
  final String tickPath;

  /// Runs every job due as of [now] and returns the server's answer.
  Future<Map<String, Object?>> runDueJobs(DateTime now) =>
      client.postJson(tickPath, body: {'now': jiso(now)});
}
