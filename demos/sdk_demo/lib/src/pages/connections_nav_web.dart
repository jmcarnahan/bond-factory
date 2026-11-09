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
///
/// Returns null on success, else the failure text. `replaceState` takes three
/// arguments (state, title, url) and the current state is passed back so the
/// router's own entry data survives. A Dart `null` in `callMethod`'s optional
/// parameters counts as "not given", so the arguments go as an explicit list.
String? replaceAddress(Uri url) {
  try {
    final target = '${url.path.isEmpty ? '/' : url.path}${url.hasQuery ? '?${url.query}' : ''}'
        '${url.hasFragment ? '#${url.fragment}' : ''}';
    final history = globalContext.getProperty<JSObject>('history'.toJS);
    final state = history.getProperty<JSAny?>('state'.toJS);
    history.callMethodVarArgs<JSAny?>('replaceState'.toJS, [state, ''.toJS, target.toJS]);
    return null;
  } catch (e) {
    return 'Could not clean the address bar: $e';
  }
}
