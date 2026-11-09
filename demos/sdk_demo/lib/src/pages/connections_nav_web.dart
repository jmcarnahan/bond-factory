import 'dart:js_interop';
import 'dart:js_interop_unsafe';

/// Sends the whole browser window to [url] (`window.location.href = url`), a
/// top-level navigation: the API session cookie rides along, which is what
/// binds the connect flow to this browser. Done with `dart:js_interop` because
/// `package:web` is not a dependency of the demo.
bool navigateTopLevel(Uri url) {
  final location = globalContext.getProperty<JSObject>('location'.toJS);
  location.setProperty('href'.toJS, url.toString().toJS);
  return true;
}

/// Puts [url] in the address bar without a new page load or history entry
/// (`history.replaceState`), so a reload no longer carries the return query.
/// Only the path, query and fragment are used: the origin cannot change.
void replaceAddress(Uri url) {
  final target = '${url.path.isEmpty ? '/' : url.path}${url.hasQuery ? '?${url.query}' : ''}'
      '${url.hasFragment ? '#${url.fragment}' : ''}';
  final history = globalContext.getProperty<JSObject>('history'.toJS);
  history.callMethod<JSAny?>('replaceState'.toJS, null, ''.toJS, target.toJS);
}
