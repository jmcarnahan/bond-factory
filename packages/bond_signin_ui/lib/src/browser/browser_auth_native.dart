import 'package:flutter_web_auth_2/flutter_web_auth_2.dart';

import 'browser_auth_base.dart';

BrowserAuth createBrowserAuth() => const NativeBrowserAuth();

/// Signature of `FlutterWebAuth2.authenticate`, injectable for tests.
typedef AuthenticateFn = Future<String> Function({
  required String url,
  required String callbackUrlScheme,
  FlutterWebAuth2Options options,
});

/// The system authentication session through `flutter_web_auth_2`
/// (ASWebAuthenticationSession on iOS, Chrome Auth Tab or Custom Tab on
/// Android). With an https [callback] (universal or app link) the host and
/// path are passed so only this app's session receives the return; with a
/// custom scheme only the scheme is.
class NativeBrowserAuth implements BrowserAuth {
  const NativeBrowserAuth({AuthenticateFn authenticate = FlutterWebAuth2.authenticate}) : _authenticate = authenticate;

  final AuthenticateFn _authenticate;

  @override
  Future<Uri> run(Uri url, {required Uri callback, bool ephemeral = false}) async {
    final https = callback.scheme == 'https';
    final result = await _authenticate(
      url: url.toString(),
      callbackUrlScheme: callback.scheme,
      options: https
          ? FlutterWebAuth2Options(httpsHost: callback.host, httpsPath: callback.path, preferEphemeral: ephemeral)
          : FlutterWebAuth2Options(preferEphemeral: ephemeral),
    );
    return Uri.parse(result);
  }
}

/// No address bar outside a browser: nothing to replace.
String? replaceAddress(Uri url) => null;
