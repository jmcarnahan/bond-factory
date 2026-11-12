/// [TaskRepository] over the synced SQLite store.
library;

import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:bond_tasks/bond_tasks.dart';

class PowerSyncTaskRepository implements TaskRepository {
  PowerSyncTaskRepository(this.db, {required this.userId, this.clock = const TaskClock()});

  final SyncDb db;
  final String userId;
  final TaskClock clock;

  @override
  Stream<List<Task>> watchOpen() => throw UnimplementedError('PowerSyncTaskRepository.watchOpen is not implemented yet');

  @override
  Future<TaskToday> today() => throw UnimplementedError('PowerSyncTaskRepository.today is not implemented yet');

  @override
  Future<TaskPage> list(TaskFilters f) => throw UnimplementedError('PowerSyncTaskRepository.list is not implemented yet');

  @override
  Future<TaskSummary> summary() => throw UnimplementedError('PowerSyncTaskRepository.summary is not implemented yet');

  @override
  Future<Task> create(TaskDraft d) => throw UnimplementedError('PowerSyncTaskRepository.create is not implemented yet');

  @override
  Future<Task> update(String id, TaskPatch p) => throw UnimplementedError('PowerSyncTaskRepository.update is not implemented yet');

  @override
  Future<Task> complete(String id) => throw UnimplementedError('PowerSyncTaskRepository.complete is not implemented yet');

  @override
  Future<Task> reopen(String id) => throw UnimplementedError('PowerSyncTaskRepository.reopen is not implemented yet');

  @override
  Future<Task> cancel(String id) => throw UnimplementedError('PowerSyncTaskRepository.cancel is not implemented yet');

  @override
  Future<void> delete(String id) => throw UnimplementedError('PowerSyncTaskRepository.delete is not implemented yet');

  @override
  Future<void> refresh() => throw UnimplementedError('PowerSyncTaskRepository.refresh is not implemented yet');

  @override
  void dispose() {}
}
