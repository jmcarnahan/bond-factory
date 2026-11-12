/// Finds app records a task can link to (people, loans, ...).
library;

import 'task.dart';

abstract interface class LinkSearch {
  Future<List<TaskLink>> search(String kind, String query);
}
