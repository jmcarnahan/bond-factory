/// Taps on a remote notification or on one of its action buttons.
library;

import 'dart:async';

import 'push_plugin.dart';

class PushTap {
  const PushTap({this.route, this.noticeId, this.action});

  final String? route;
  final String? noticeId;

  /// `done`, `snooze` or `cancel`; null for a plain tap.
  final String? action;

  @override
  bool operator ==(Object other) =>
      other is PushTap && other.route == route && other.noticeId == noticeId && other.action == action;

  @override
  int get hashCode => Object.hash(route, noticeId, action);
}

abstract interface class PushTaps {
  Stream<PushTap> get taps;

  /// The tap that launched the app from a terminated state, if any.
  Future<PushTap?> initialTap();
}

class NoPushTaps implements PushTaps {
  const NoPushTaps();

  @override
  Stream<PushTap> get taps => const Stream<PushTap>.empty();

  @override
  Future<PushTap?> initialTap() async => null;
}

/// Taps over the pub.dev `push` plugin.
///
/// The payload is `{notice_id, task_id, route}` (top level, or under `data`).
/// [PushTap.action] is always null: the plugin does not report which action
/// button was pressed, so a tap on a button looks like a plain tap and opens
/// the task. A payload with neither a notice id nor a route is not ours and is ignored.
class PluginPushTaps implements PushTaps {
  PluginPushTaps({PushPlugin? plugin}) : _plugin = plugin ?? const DefaultPushPlugin();

  final PushPlugin _plugin;

  static PushTap? parse(Map<String?, Object?>? payload) {
    if (payload == null) return null;
    String? pick(String k) {
      final nested = payload['data'];
      final v = payload[k] ?? (nested is Map ? nested[k] : null);
      return v is String && v.isNotEmpty ? v : null;
    }

    final notice = pick('notice_id');
    final route = pick('route');
    if (notice == null && route == null) return null;
    return PushTap(route: route, noticeId: notice);
  }

  @override
  Stream<PushTap> get taps {
    void Function()? off;
    late StreamController<PushTap> c;
    c = StreamController<PushTap>.broadcast(
      onListen: () => off = _plugin.addOnNotificationTap((p) {
        final t = parse(p);
        if (t != null) c.add(t);
      }),
      onCancel: () {
        off?.call();
        off = null;
      },
    );
    return c.stream;
  }

  @override
  Future<PushTap?> initialTap() async => parse(await _plugin.launchTap());
}
