/// [TaskRepository] over [TasksApi]: the path with no sync store.
library;

import 'task.dart';
import 'task_clock.dart';
import 'task_draft.dart';
import 'task_filters.dart';
import 'task_repository.dart';
import 'task_today.dart';
import 'tasks_api.dart';

class RemoteTaskRepository implements TaskRepository {
  RemoteTaskRepository(this.api, {this.clock = const TaskClock(), this.timeZone});

  final TasksApi api;
  final TaskClock clock;

  /// The device's IANA zone name, read for every call.
  final String? Function()? timeZone;

  @override
  Stream<List<Task>> watchOpen() => throw UnimplementedError('RemoteTaskRepository.watchOpen is not implemented yet');

  @override
  Future<TaskToday> today() => throw UnimplementedError('RemoteTaskRepository.today is not implemented yet');

  @override
  Future<TaskPage> list(TaskFilters f) => throw UnimplementedError('RemoteTaskRepository.list is not implemented yet');

  @override
  Future<TaskSummary> summary() => throw UnimplementedError('RemoteTaskRepository.summary is not implemented yet');

  @override
  Future<Task> create(TaskDraft d) => throw UnimplementedError('RemoteTaskRepository.create is not implemented yet');

  @override
  Future<Task> update(String id, TaskPatch p) => throw UnimplementedError('RemoteTaskRepository.update is not implemented yet');

  @override
  Future<Task> complete(String id) => throw UnimplementedError('RemoteTaskRepository.complete is not implemented yet');

  @override
  Future<Task> reopen(String id) => throw UnimplementedError('RemoteTaskRepository.reopen is not implemented yet');

  @override
  Future<Task> cancel(String id) => throw UnimplementedError('RemoteTaskRepository.cancel is not implemented yet');

  @override
  Future<void> delete(String id) => throw UnimplementedError('RemoteTaskRepository.delete is not implemented yet');

  @override
  Future<void> refresh() => throw UnimplementedError('RemoteTaskRepository.refresh is not implemented yet');

  @override
  void dispose() {}
}
