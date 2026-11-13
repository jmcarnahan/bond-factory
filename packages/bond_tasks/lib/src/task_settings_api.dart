/// HTTP client of the per-user task settings.
library;

import 'package:bond_api/bond_api.dart';

import 'task_settings.dart';
import 'task_settings_store.dart';

class TaskSettingsApi implements TaskSettingsStore {
  TaskSettingsApi(this.client, {this.prefix = '/tasks/settings'});

  final ApiClient client;
  final String prefix;

  @override
  Future<TaskSettings> get() async => TaskSettings.fromJson(await client.getJson(prefix));

  @override
  Future<TaskSettings> update(TaskSettingsPatch p) async =>
      TaskSettings.fromJson(await client.putJson(prefix, body: p.toJson()));
}
