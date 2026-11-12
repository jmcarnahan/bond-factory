/// HTTP client of the per-user task settings.
library;

import 'package:bond_api/bond_api.dart';

import 'task_settings.dart';

class TaskSettingsApi {
  TaskSettingsApi(this.client, {this.prefix = '/tasks/settings'});

  final ApiClient client;
  final String prefix;

  Future<TaskSettings> get() async => TaskSettings.fromJson(await client.getJson(prefix));

  Future<TaskSettings> update(TaskSettingsPatch p) async =>
      TaskSettings.fromJson(await client.putJson(prefix, body: p.toJson()));
}
