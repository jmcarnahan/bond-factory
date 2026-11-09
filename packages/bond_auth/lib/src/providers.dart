/// `GET /auth/providers`: which sign-in methods the server offers, and the
/// public client config of the identity provider.
library;

import 'package:bond_json/bond_json.dart';

/// Public web-app config of the identity provider.
class FirebaseWebConfig {
  const FirebaseWebConfig({required this.apiKey, required this.appId});

  final String apiKey;
  final String appId;
}

/// Public iOS-app config of the identity provider.
class FirebaseIosConfig {
  const FirebaseIosConfig({required this.apiKey, required this.appId, required this.bundleId});

  final String apiKey;
  final String appId;
  final String bundleId;
}

/// The identity provider's public client config, read at runtime so no
/// generated options file is compiled into the app.
class FirebaseRuntimeConfig {
  const FirebaseRuntimeConfig({
    required this.projectId,
    required this.authDomain,
    required this.messagingSenderId,
    this.web,
    this.ios,
  });

  /// Reads the `firebase` object of the providers answer ([providers] is the
  /// whole answer). Null when it is absent, has no project id, or neither
  /// platform block is complete.
  static FirebaseRuntimeConfig? fromProviders(Map<Object?, Object?> providers) {
    final f = jmap(providers, 'firebase');
    if (f == null) return null;
    final projectId = _text(f, 'project_id');
    if (projectId.isEmpty) return null;
    final webJson = jmap(f, 'web');
    final iosJson = jmap(f, 'ios');
    final webKey = webJson == null ? '' : _text(webJson, 'api_key');
    final webApp = webJson == null ? '' : _text(webJson, 'app_id');
    final iosKey = iosJson == null ? '' : _text(iosJson, 'api_key');
    final iosApp = iosJson == null ? '' : _text(iosJson, 'app_id');
    final iosBundle = iosJson == null ? '' : _text(iosJson, 'bundle_id');
    final config = FirebaseRuntimeConfig(
      projectId: projectId,
      authDomain: _text(f, 'auth_domain'),
      messagingSenderId: _text(f, 'messaging_sender_id'),
      web: webKey.isEmpty || webApp.isEmpty ? null : FirebaseWebConfig(apiKey: webKey, appId: webApp),
      ios: iosKey.isEmpty || iosApp.isEmpty || iosBundle.isEmpty
          ? null
          : FirebaseIosConfig(apiKey: iosKey, appId: iosApp, bundleId: iosBundle),
    );
    return config.webComplete || config.iosComplete ? config : null;
  }

  static String _text(Map<Object?, Object?> m, String k) => jstr(m, k) ?? '';

  final String projectId;
  final String authDomain;
  final String messagingSenderId;
  final FirebaseWebConfig? web;
  final FirebaseIosConfig? ios;

  /// Enough to initialise the browser SDK.
  bool get webComplete => web != null && authDomain.isNotEmpty && messagingSenderId.isNotEmpty;

  /// Enough to initialise the iOS SDK.
  bool get iosComplete => ios != null && messagingSenderId.isNotEmpty;
}

/// One direct sign-in method the server offers: `{id, label}`.
class SignInProvider {
  const SignInProvider({required this.id, required this.label});

  /// The registered provider name (`google`, `microsoft`).
  final String id;

  /// The button text the server suggests.
  final String label;
}

/// The merged providers answer.
class AuthProviders {
  const AuthProviders({
    this.demo = false,
    this.emailPassword = false,
    this.google = false,
    this.googleWebClientId,
    this.apple = false,
    this.mock = false,
    this.firebase,
    this.syncUrl,
    this.signin = const [],
    this.breakGlass = false,
    this.defaultFlow = 'firebase',
  });

  factory AuthProviders.fromJson(Map<Object?, Object?> json) {
    final sync = jmap(json, 'sync');
    final url = sync == null ? null : jstr(sync, 'url');
    return AuthProviders(
      demo: jbool(json, 'demo') ?? false,
      emailPassword: jbool(json, 'email_password') ?? false,
      google: jbool(json, 'google') ?? false,
      googleWebClientId: jstr(json, 'google_web_client_id'),
      apple: jbool(json, 'apple') ?? false,
      mock: jbool(json, 'mock') ?? false,
      firebase: FirebaseRuntimeConfig.fromProviders(json),
      syncUrl: url == null || url.isEmpty ? null : Uri.tryParse(url),
      signin: _signin(json),
      breakGlass: jbool(json, 'break_glass') ?? false,
      defaultFlow: jstr(json, 'default_flow') ?? 'firebase',
    );
  }

  static List<SignInProvider> _signin(Map<Object?, Object?> json) {
    final raw = json['signin'];
    if (raw is! List) return const [];
    return [
      for (final e in raw)
        if (e is Map && jstr(e, 'id') != null && jstr(e, 'id')!.isNotEmpty)
          SignInProvider(id: jstr(e, 'id')!, label: jstr(e, 'label') ?? jstr(e, 'id')!),
    ];
  }

  final bool demo;
  final bool emailPassword;
  final bool google;
  final String? googleWebClientId;
  final bool apple;
  final bool mock;
  final FirebaseRuntimeConfig? firebase;
  final Uri? syncUrl;

  /// Direct sign-in methods on offer (`signin` key); empty when absent.
  final List<SignInProvider> signin;

  /// True when the e-mail and password break-glass sign-in is on (`break_glass`).
  final bool breakGlass;

  /// Which flow the app starts with: `firebase` or `signin` (`default_flow`).
  final String defaultFlow;

  /// The direct sign-in method with registered name [id], or null when the
  /// server does not offer it.
  SignInProvider? signinById(String id) {
    for (final p in signin) {
      if (p.id == id) return p;
    }
    return null;
  }
}
