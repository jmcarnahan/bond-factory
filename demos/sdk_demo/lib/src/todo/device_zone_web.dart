import 'dart:js_interop';

@JS('Intl.DateTimeFormat')
extension type _Format._(JSObject _) implements JSObject {
  external factory _Format();
  external _Options resolvedOptions();
}

extension type _Options._(JSObject _) implements JSObject {
  external String? get timeZone;
}

/// The browser's IANA zone name (`Intl.DateTimeFormat().resolvedOptions().timeZone`).
String? deviceZoneName() {
  try {
    final zone = _Format().resolvedOptions().timeZone;
    return zone == null || zone.isEmpty ? null : zone;
  } on Object {
    return null;
  }
}
