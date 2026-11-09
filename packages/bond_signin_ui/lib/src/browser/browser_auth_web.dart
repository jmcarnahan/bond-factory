import 'dart:async';
import 'dart:js_interop';
import 'dart:js_interop_unsafe';

import 'browser_auth_base.dart';

BrowserAuth createBrowserAuth() => const WebBrowserAuth();

/// Sends the whole browser window to the provider's address
/// (`window.location.href`), a top-level navigation: the cookie the start call
/// set rides along, which is what binds the flow to this browser. [run] never
/// completes because the page unloads; the app reads the return on the next
/// load. Done with `dart:js_interop` so `package:web` is not needed.
class WebBrowserAuth implements BrowserAuth {
  const WebBrowserAuth();

  @override
  Future<Uri> run(Uri url, {required Uri callback, bool ephemeral = false}) {
    final location = globalContext.getProperty<JSObject>('location'.toJS);
    location.setProperty('href'.toJS, url.toString().toJS);
    return Completer<Uri>().future; // never completes: the page is leaving
  }
}

/// `history.replaceState` with the current state passed back so the router's
/// own entry data survives. `callMethod`'s optional parameters treat Dart
/// `null` as "not given", so the arguments go as an explicit list.
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
