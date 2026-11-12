/// [PushDevices] as local writes that the sync upload carries.
library;

import 'package:bond_push/bond_push.dart';
import 'package:bond_sync_powersync/bond_sync_powersync.dart';

class SyncPushDevices implements PushDevices {
  SyncPushDevices(this.db, {required this.userId});

  final SyncDb db;
  final String userId;

  @override
  Future<void> register(PushToken t, {required String deviceId, String? topic}) =>
      throw UnimplementedError('SyncPushDevices.register is not implemented yet');

  @override
  Future<void> unregister(String deviceId) => throw UnimplementedError('SyncPushDevices.unregister is not implemented yet');
}
