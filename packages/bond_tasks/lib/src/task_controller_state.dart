/// Immutable state of the task controller.
library;

import 'task.dart';
import 'task_today.dart';

class TaskControllerState {
  const TaskControllerState({
    this.open = const [],
    this.today,
    this.loading = false,
    this.error,
    this.undoTaskId,
  });

  final List<Task> open;
  final TaskToday? today;
  final bool loading;
  final Object? error;

  /// The task just completed, which [TaskController.undo] reopens; null when nothing can be undone.
  final String? undoTaskId;

  TaskControllerState copyWith({
    List<Task>? open,
    TaskToday? today,
    bool? loading,
    Object? error,
    String? undoTaskId,
    bool clearError = false,
    bool clearUndo = false,
  }) =>
      TaskControllerState(
        open: open ?? this.open,
        today: today ?? this.today,
        loading: loading ?? this.loading,
        error: clearError ? null : (error ?? this.error),
        undoTaskId: clearUndo ? null : (undoTaskId ?? this.undoTaskId),
      );
}
