import 'package:bond_signin_ui/bond_signin_ui.dart';
import 'package:flutter_web_auth_2/flutter_web_auth_2.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:bond_signin_ui/src/browser/browser_auth_native.dart' show NativeBrowserAuth;

void main() {
  late String? gotUrl;
  late String? gotScheme;
  late FlutterWebAuth2Options? gotOptions;

  NativeBrowserAuth fake(String result) => NativeBrowserAuth(authenticate: ({required url, required callbackUrlScheme, options = const FlutterWebAuth2Options()}) async {
        gotUrl = url;
        gotScheme = callbackUrlScheme;
        gotOptions = options;
        return result;
      });

  test('an https callback passes host and path and the scheme https', () async {
    final out = await fake('https://api.test/app/return/google?attempt=a&code=c')
        .run(Uri.parse('https://idp.test/a'), callback: Uri.parse('https://api.test/app/return/google'));
    expect(gotUrl, 'https://idp.test/a');
    expect(gotScheme, 'https');
    expect([gotOptions!.httpsHost, gotOptions!.httpsPath, gotOptions!.preferEphemeral], ['api.test', '/app/return/google', false]);
    expect(out.queryParameters['code'], 'c');
  });

  test('a custom scheme passes only the scheme, ephemeral when asked', () async {
    await fake('sdkdemo://return/google?attempt=a&code=c')
        .run(Uri.parse('https://idp.test/a'), callback: Uri.parse('sdkdemo://return/google'), ephemeral: true);
    expect(gotScheme, 'sdkdemo');
    expect([gotOptions!.httpsHost, gotOptions!.httpsPath, gotOptions!.preferEphemeral], [null, null, true]);
  });

  test('defaultBrowserAuth is the native one on the VM and replaceAddress is a no-op', () {
    expect(defaultBrowserAuth(), isA<NativeBrowserAuth>());
    expect(replaceAddress(Uri.parse('/x')), isNull);
  });

  test('NativeReturn picks by capability and refuses a missing scheme', () {
    final https = Uri.parse('https://api.test/app/return/google');
    final scheme = Uri.parse('sdkdemo://return/google');
    expect(NativeReturn.choose(httpsReturn: https, schemeReturn: scheme, httpsSupported: true), https);
    expect(NativeReturn.choose(httpsReturn: https, schemeReturn: scheme, httpsSupported: false), scheme);
    expect(() => NativeReturn.choose(httpsReturn: https, httpsSupported: false), throwsStateError);
  });
}
