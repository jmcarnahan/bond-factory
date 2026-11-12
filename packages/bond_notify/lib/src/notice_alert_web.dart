import 'notice.dart';
import 'notice_alert.dart';

// Not implemented yet: this will call the browser's Notification API through dart:js_interop.
NoticeAlert createNoticeAlert() => const _NoopWebAlert();

class _NoopWebAlert implements NoticeAlert {
  const _NoopWebAlert();

  @override
  Future<bool> requestPermission() async => false;

  @override
  void show(Notice n) {}
}
