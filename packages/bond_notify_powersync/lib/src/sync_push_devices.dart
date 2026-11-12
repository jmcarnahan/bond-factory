/// [PushDevices] as local writes that the sync upload carries.
library;

import 'dart:convert';

import 'package:bond_push/bond_push.dart';
import 'package:bond_sync_powersync/bond_sync_powersync.dart';

import 'package:crypto/crypto.dart';

import 'notify_tables.dart';

String _isoZ(DateTime t) => DateTime.fromMillisecondsSinceEpoch(t.millisecondsSinceEpoch, isUtc: true).toIso8601String();

/// Registers this device by writing its own `push_devices` row.
///
/// The row id is `d_` plus the first 32 hex characters of sha256 of `<userId>|<deviceId>`: one row per
/// user and device, always inside the sync id rule `[A-Za-z0-9_-]{1,64}` whatever the ids hold, so
/// registering twice is an update of the same row (a token refresh is a patch of `token` and the
/// channel columns). `user_id` is written on insert, but the server sets it from the session; the
/// server also owns `last_seen_at` and `disabled_at`, so an update never writes them. Unregister
/// deletes the row.
class SyncPushDevices implements PushDevices {
  SyncPushDevices(this.db, {required this.userId, DateTime Function()? now}) : _now = now ?? DateTime.now;

  final SyncDb db;
  final String userId;
  final DateTime Function() _now;

  /// The row id for [deviceId].
  String rowId(String deviceId) => 'd_${sha256.convert(utf8.encode('$userId|$deviceId')).toString().substring(0, 32)}';

  @override
  Future<void> register(PushToken t, {required String deviceId, String? topic}) => db.writeTransaction((tx) async {
        final id = rowId(deviceId);
        final now = _isoZ(_now());
        final existing = await tx.getOptional('SELECT id FROM $kPushDevicesTable WHERE id = ?', [id]);
        if (existing == null) {
          await tx.execute(
            'INSERT INTO $kPushDevicesTable (id, user_id, device_id, token, platform, environment, topic, '
            'last_seen_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            [id, userId, deviceId, t.value, t.platform, t.environment, topic, now, now],
          );
        } else {
          await tx.execute(
            'UPDATE $kPushDevicesTable SET token = ?, platform = ?, environment = ?, topic = ? '
            'WHERE id = ? AND user_id = ?',
            [t.value, t.platform, t.environment, topic, id, userId],
          );
        }
      });

  @override
  Future<void> unregister(String deviceId) => db.writeTransaction(
        (tx) => tx.execute('DELETE FROM $kPushDevicesTable WHERE id = ? AND user_id = ?', [rowId(deviceId), userId]),
      );
}
