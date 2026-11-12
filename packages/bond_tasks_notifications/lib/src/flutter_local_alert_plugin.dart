/// [AlertPlugin] over flutter_local_notifications (iOS only).
///
/// Every platform call lives in this file. It cannot be unit-tested (platform
/// channels), so it stays thin: all logic is tested through FakeAlertPlugin.
library;

import 'package:bond_tasks/bond_tasks.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart' as fln;
import 'package:timezone/data/latest_all.dart' as tzdata;
import 'package:timezone/timezone.dart' as tz;

import 'alert_labels.dart';
import 'alert_plugin.dart';

class FlutterLocalAlertPlugin implements AlertPlugin {
  FlutterLocalAlertPlugin({fln.FlutterLocalNotificationsPlugin? plugin, this.labels = const AlertLabels()})
      : _plugin = plugin ?? fln.FlutterLocalNotificationsPlugin();

  final fln.FlutterLocalNotificationsPlugin _plugin;
  final AlertLabels labels;

  fln.IOSFlutterLocalNotificationsPlugin? get _ios =>
      _plugin.resolvePlatformSpecificImplementation<fln.IOSFlutterLocalNotificationsPlugin>();

  /// Registers two categories (`bond.task`: Done, Snooze; `bond.task.owner`: plus Cancel), all
  /// opening the app. No permission is requested here.
  @override
  Future<void> init({required void Function(AlertTap) onTap}) async {
    tzdata.initializeTimeZones();
    const fg = {fln.DarwinNotificationActionOption.foreground};
    await _plugin.initialize(
      settings: fln.InitializationSettings(
        iOS: fln.DarwinInitializationSettings(
          requestAlertPermission: false,
          requestSoundPermission: false,
          requestBadgePermission: false,
          defaultPresentBadge: false,
          notificationCategories: [
            fln.DarwinNotificationCategory(kNoticeCategory, actions: [
              fln.DarwinNotificationAction.plain(NoticeAction.done.wire, labels.done, options: fg),
              fln.DarwinNotificationAction.plain(NoticeAction.snooze.wire, labels.snooze, options: fg),
            ]),
            fln.DarwinNotificationCategory(kNoticeCategoryOwner, actions: [
              fln.DarwinNotificationAction.plain(NoticeAction.done.wire, labels.done, options: fg),
              fln.DarwinNotificationAction.plain(NoticeAction.snooze.wire, labels.snooze, options: fg),
              fln.DarwinNotificationAction.plain(NoticeAction.cancel.wire, labels.cancel, options: fg),
            ]),
          ],
        ),
      ),
      onDidReceiveNotificationResponse: (r) {
        final tap = AlertTap.fromPayload(r.payload, action: NoticeAction.fromWire(r.actionId));
        if (tap != null) onTap(tap);
      },
    );
  }

  @override
  Future<bool> requestPermission() async =>
      await _ios?.requestPermissions(alert: true, sound: true, badge: false) ?? false;

  fln.NotificationDetails _details(AlertRequest r) => fln.NotificationDetails(
        iOS: fln.DarwinNotificationDetails(
          categoryIdentifier: categoryFor(r),
          threadIdentifier: r.taskId,
          presentAlert: true,
          presentBanner: true,
          presentList: true,
          presentSound: true,
          presentBadge: false,
        ),
      );

  String _payload(AlertRequest r) => AlertTap(noticeId: r.noticeId, taskId: r.taskId, route: r.route).toPayload();

  @override
  Future<void> schedule(AlertRequest r) => _plugin.zonedSchedule(
        id: r.id,
        title: r.title,
        body: r.body,
        scheduledDate: tz.TZDateTime.from(r.atUtc.toUtc(), tz.UTC),
        notificationDetails: _details(r),
        // The plugin's API requires this argument; it is unused on iOS.
        androidScheduleMode: fln.AndroidScheduleMode.inexactAllowWhileIdle,
        payload: _payload(r),
      );

  @override
  Future<void> show(AlertRequest r) => _plugin.show(
        id: r.id,
        title: r.title,
        body: r.body,
        notificationDetails: _details(r),
        payload: _payload(r),
      );

  @override
  Future<void> cancel(int id) => _plugin.cancel(id: id);

  @override
  Future<List<PendingAlert>> pending() async {
    final list = await _plugin.pendingNotificationRequests();
    return [for (final p in list) PendingAlert(id: p.id, payload: p.payload)];
  }

  @override
  Future<List<int>> active() async {
    final list = await _plugin.getActiveNotifications();
    return [
      for (final a in list)
        if (a.id != null) a.id!,
    ];
  }

  @override
  Future<AlertTap?> launchTap() async {
    try {
      final d = await _plugin.getNotificationAppLaunchDetails();
      final r = d?.notificationResponse;
      if (d == null || !d.didNotificationLaunchApp || r == null) return null;
      return AlertTap.fromPayload(r.payload, action: NoticeAction.fromWire(r.actionId));
    } catch (_) {
      return null;
    }
  }
}
