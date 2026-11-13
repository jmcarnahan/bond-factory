import 'package:bond_sync_powersync/testing.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_powersync/bond_tasks_powersync.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('every settings name exists, and the store is a TaskSettingsStore', () {
    expect(kTaskSettingsTable, 'task_user_settings');
    expect(kTaskSettingsColumns, hasLength(4));
    expect(taskSettingsTables(), hasLength(1));
    final TaskSettingsStore store = PowerSyncTaskSettingsStore(FakeSyncDb(), userId: 'u');
    expect(store, isA<PowerSyncTaskSettingsStore>());
    expect((store as PowerSyncTaskSettingsStore).watch, isA<Function>());
    expect(store.get, isA<Function>());
    expect(store.update, isA<Function>());
  });
}
