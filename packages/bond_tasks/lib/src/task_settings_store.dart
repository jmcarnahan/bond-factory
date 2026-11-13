/// Where the per-user task settings are read and written (HTTP, or a local database that syncs).
library;

import 'task_settings.dart';

abstract interface class TaskSettingsStore {
  Future<TaskSettings> get();
  Future<TaskSettings> update(TaskSettingsPatch p);
}
