import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:powersync/powersync.dart';

void main() {
  test('the barrel exports the adapter names and the core path helpers', () {
    final policy = SyncPolicy(schema: Schema(syncSupportTables()));
    expect(policy.schemaTables, isEmpty);
    expect(SyncConnector, isNotNull);
    expect(PowerSyncSyncStore, isNotNull);
    expect(syncDbPath('/d', 'u', prefix: 'x'), '/d/x_u.db');
    expect(const BondSyncNames().prefix, 'bond');
  });
}
