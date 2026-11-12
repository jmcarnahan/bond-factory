import 'package:bond_notify_powersync/bond_notify_powersync.dart';
import 'package:bond_push/bond_push.dart';
import 'package:bond_sync_powersync/testing.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('public names exist and nothing is left unimplemented', () async {
    expect(kNoticesTable, 'notices');
    expect(kPushDevicesTable, 'push_devices');
    expect(noticesTables(), hasLength(1));
    expect(pushDevicesTables(), hasLength(1));
    final feed = WatchNoticeFeed(FakeSyncDb(), userId: 'u');
    await feed.refresh();
    feed.dispose();
    final devices = SyncPushDevices(FakeSyncDb(), userId: 'u');
    await devices.unregister('d');
    await devices.register(const PushToken(value: 'x'), deviceId: 'd');
  });
}
