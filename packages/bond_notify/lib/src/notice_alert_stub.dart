import 'notice.dart';
import 'notice_alert.dart';

NoticeAlert createNoticeAlert() => const _NoopNoticeAlert();

class _NoopNoticeAlert implements NoticeAlert {
  const _NoopNoticeAlert();

  @override
  Future<bool> requestPermission() async => false;

  @override
  void show(Notice n) {}
}
