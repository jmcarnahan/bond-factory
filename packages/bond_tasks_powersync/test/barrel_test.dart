import 'package:bond_sync_powersync/testing.dart';
import 'package:bond_tasks_powersync/bond_tasks_powersync.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('shell names exist', () {
    expect(kTasksTable, 'tasks');
    expect(tasksTables, throwsUnimplementedError);
    final repo = PowerSyncTaskRepository(FakeSyncDb(), userId: 'u');
    expect(repo.userId, 'u');
    expect(repo.refresh, throwsUnimplementedError);
    repo.dispose();
  });
}
