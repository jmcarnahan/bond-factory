/// `GET /tasks/today`.
library;

import 'package:bond_json/bond_json.dart';

import 'task.dart';
import 'task_filters.dart';

class TaskTodayCounts {
  const TaskTodayCounts({this.overdue = 0, this.today = 0, this.undated = 0, this.doneToday = 0});

  factory TaskTodayCounts.fromJson(Map<String, Object?> m) => TaskTodayCounts(
        overdue: jint(m, 'overdue') ?? 0,
        today: jint(m, 'today') ?? 0,
        undated: jint(m, 'undated') ?? 0,
        doneToday: jint(m, 'done_today') ?? 0,
      );

  final int overdue;
  final int today;
  final int undated;
  final int doneToday;

  Map<String, Object?> toJson() => {'overdue': overdue, 'today': today, 'undated': undated, 'done_today': doneToday};
}

/// The day view: exclusive sections of open tasks plus what was done today.
class TaskToday {
  const TaskToday({
    this.overdue = const [],
    this.today = const [],
    this.undated = const [],
    this.doneToday = const [],
    this.counts = const TaskTodayCounts(),
  });

  factory TaskToday.fromJson(Map<String, Object?> m) {
    List<Task> tasks(String k) => jlist(m, k, (o) => Task.fromJson(jmapOf(o)));
    return TaskToday(
      overdue: tasks('overdue'),
      today: tasks('today'),
      undated: tasks('undated'),
      doneToday: tasks('done_today'),
      counts: TaskTodayCounts.fromJson(jmap(m, 'counts') ?? const {}),
    );
  }

  final List<Task> overdue;
  final List<Task> today;
  final List<Task> undated;
  final List<Task> doneToday;
  final TaskTodayCounts counts;

  Map<String, Object?> toJson() => {
        'overdue': [for (final t in overdue) t.toJson()],
        'today': [for (final t in today) t.toJson()],
        'undated': [for (final t in undated) t.toJson()],
        'done_today': [for (final t in doneToday) t.toJson()],
        'counts': counts.toJson(),
      };
}
