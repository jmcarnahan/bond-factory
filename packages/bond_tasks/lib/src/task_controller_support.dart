/// Helpers of [TaskController] kept apart to keep that file short. Not exported.
library;

import 'task.dart';
import 'task_controller_state.dart';

/// Which task sits in which section with which flag; equal shapes mean nothing to emit.
String controllerShape(TaskControllerState s) {
  String of(String name, List<Task> l) => '$name:${[for (final t in l) '${t.id}${t.overdue ? '!' : ''}'].join(',')}';
  final t = s.today;
  return [
    of('o', s.open),
    if (t != null) ...[
      of('a', t.overdue),
      of('t', t.today),
      of('u', t.undated),
      '${t.counts.overdue}/${t.counts.today}/${t.counts.undated}',
    ],
  ].join('|');
}

/// [cur] with [task] put back before the first task of [order] that followed it and is still in [cur],
/// else after the nearest one that preceded it, else at the end.
List<Task> insertInOrder(List<Task> cur, Task task, List<String> order) {
  final out = [
    for (final t in cur)
      if (t.id != task.id) t,
  ];
  final at = order.indexOf(task.id);
  if (at >= 0) {
    for (var i = at + 1; i < order.length; i++) {
      final j = out.indexWhere((t) => t.id == order[i]);
      if (j >= 0) return out..insert(j, task);
    }
    for (var i = at - 1; i >= 0; i--) {
      final j = out.indexWhere((t) => t.id == order[i]);
      if (j >= 0) return out..insert(j + 1, task);
    }
  }
  return out..add(task);
}

/// A task taken out of the lists by `complete`, with the ids around it so it can be put back in place.
class RemovedTask {
  const RemovedTask(this.task, this.openOrder, this.sectionOrder);
  final Task task;

  /// The ids of the open list, and of the day sections flattened, as they were just before removal.
  final List<String> openOrder;
  final List<String> sectionOrder;
}
