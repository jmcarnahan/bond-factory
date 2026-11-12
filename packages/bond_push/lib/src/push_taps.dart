/// Taps on a remote notification or on one of its action buttons.
library;

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
