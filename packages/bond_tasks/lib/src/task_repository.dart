/// Where the controller reads and writes tasks (REST, or a sync store).
library;

import 'task.dart';
import 'task_draft.dart';
import 'task_filters.dart';
import 'task_today.dart';

abstract interface class TaskRepository {
  Stream<List<Task>> watchOpen();
  Future<TaskToday> today();
  Future<TaskPage> list(TaskFilters f);
  Future<TaskSummary> summary();
  Future<Task> create(TaskDraft d);
  Future<Task> update(String id, TaskPatch p);
  Future<Task> complete(String id);
  Future<Task> reopen(String id);
  Future<Task> cancel(String id);
  Future<void> delete(String id);
  Future<void> refresh();
  void dispose();
}
