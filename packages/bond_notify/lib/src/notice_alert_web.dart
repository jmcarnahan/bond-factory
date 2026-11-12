import 'dart:js_interop';
import 'dart:js_interop_unsafe';

import 'notice.dart';
import 'notice_alert.dart';

/// The browser Notification API through `dart:js_interop` (no `package:web`).
NoticeAlert createNoticeAlert() => const _WebNoticeAlert();

class _WebNoticeAlert implements NoticeAlert {
  const _WebNoticeAlert();

  static JSFunction? get _ctor {
    try {
      return globalContext.getProperty<JSFunction?>('Notification'.toJS);
    } catch (_) {
      return null;
    }
  }

  /// Asks the browser; true when the answer is "granted".
  @override
  Future<bool> requestPermission() async {
    final ctor = _ctor;
    if (ctor == null) return false;
    try {
      final obj = ctor as JSObject;
      final p = obj.callMethod<JSPromise<JSAny?>>('requestPermission'.toJS);
      final r = await p.toDart;
      return (r as JSString?)?.toDart == 'granted';
    } catch (_) {
      return false;
    }
  }

  /// Shows a system notification only when permission is granted and the page
  /// is hidden. The tag is the notice id, so a repeat replaces the earlier one.
  @override
  void show(Notice n) {
    final ctor = _ctor;
    if (ctor == null) return;
    try {
      final obj = ctor as JSObject;
      if (obj.getProperty<JSString?>('permission'.toJS)?.toDart != 'granted') return;
      final doc = globalContext.getProperty<JSObject>('document'.toJS);
      if (doc.getProperty<JSBoolean?>('hidden'.toJS)?.toDart != true) return;
      final options = <String, Object?>{'body': n.body, 'tag': n.id}.jsify();
      ctor.callAsConstructor<JSObject>(n.title.toJS, options);
    } catch (_) {
      // A browser that refuses (insecure context, blocked) simply shows nothing.
    }
  }
}
