import 'browser_auth_base.dart';
import 'browser_auth_native.dart' if (dart.library.js_interop) 'browser_auth_web.dart' as impl;

export 'browser_auth_base.dart';

/// The right [BrowserAuth] for this build, chosen at compile time by the
/// conditional import (never by `Platform`): top-level navigation on web, the
/// system authentication session elsewhere.
BrowserAuth defaultBrowserAuth() => impl.createBrowserAuth();

/// Puts [url] in the address bar without a page load or history entry, so a
/// reload no longer carries the return query. Only path, query and fragment
/// are used. Returns null on success (and outside a browser, where there is no
/// address bar), else the failure text.
String? replaceAddress(Uri url) => impl.replaceAddress(url);
