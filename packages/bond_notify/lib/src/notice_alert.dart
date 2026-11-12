/// A system-level alert for a new notice (the browser notification on web).
library;

import 'notice.dart';
import 'notice_alert_stub.dart' if (dart.library.js_interop) 'notice_alert_web.dart' as impl;

abstract interface class NoticeAlert {
  Future<bool> requestPermission();
  void show(Notice n);
}

/// The browser notification hook; a no-op outside a browser build.
NoticeAlert browserNoticeAlert() => impl.createNoticeAlert();
