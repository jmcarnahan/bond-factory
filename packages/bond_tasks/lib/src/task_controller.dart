/// Framework-free task list state: optimistic complete with undo.
library;

import 'task_clock.dart';
import 'task_controller_state.dart';
import 'task_repository.dart';

export 'task_controller_state.dart';

class TaskController {
  TaskController(this.repo, {this.clock = const TaskClock()});

  final TaskRepository repo;
  final TaskClock clock;

  Stream<TaskControllerState> get states => throw UnimplementedError('TaskController.states is not implemented yet');

  TaskControllerState get state => throw UnimplementedError('TaskController.state is not implemented yet');

  Future<void> load() => throw UnimplementedError('TaskController.load is not implemented yet');

  /// Optimistic: the task leaves the open list at once and returns if the call fails.
  Future<void> complete(String id) => throw UnimplementedError('TaskController.complete is not implemented yet');

  /// Reopens the task that [complete] last finished.
  Future<void> undo() => throw UnimplementedError('TaskController.undo is not implemented yet');

  void dispose() {}
}
