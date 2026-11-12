/// Registering a device token with the service.
library;

import 'package:bond_api/bond_api.dart';

import 'push_token.dart';

abstract interface class PushDevices {
  Future<void> register(PushToken t, {required String deviceId, String? topic});
  Future<void> unregister(String deviceId);
}

/// REST: `POST /push/devices` and `DELETE /push/devices/{device_id}`.
class PushDevicesApi implements PushDevices {
  PushDevicesApi(this.client, {this.prefix = '/push/devices'});

  final ApiClient client;
  final String prefix;

  @override
  Future<void> register(PushToken t, {required String deviceId, String? topic}) async {
    await client.postJson(prefix, body: {
      ...t.toJson(),
      'device_id': deviceId,
      'topic': ?topic,
    });
  }

  @override
  Future<void> unregister(String deviceId) async {
    await client.deleteJson('$prefix/${Uri.encodeComponent(deviceId)}');
  }
}
