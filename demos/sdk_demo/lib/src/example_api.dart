import 'package:bond_api/bond_api.dart';
import 'package:bond_auth/bond_auth.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'example_http_client_io.dart' if (dart.library.js_interop) 'example_http_client_web.dart';

/// The one session every demo page shares: a single [ApiClient] whose bearer
/// token lives in an [InMemoryTokenStore] and whose 401 renewal goes through
/// the gateway the person signed in with.
///
/// The example runs in mock mode, so the identity provider is a
/// [FakeIdTokenSource] whose id tokens read `mock:<email>`.
class DemoSession {
  const DemoSession._();

  /// Base URL of the example API; override with `--dart-define=SDK_EXAMPLE_URL=...`.
  static Uri baseUrl = Uri.parse(
    const String.fromEnvironment(
      'SDK_EXAMPLE_URL',
      defaultValue: 'http://localhost:8012',
    ),
  );

  /// The seeded user `POST /auth/demo` signs in as by default.
  static const String defaultUserId = 'demo-user-1';

  /// The seeded user's e-mail, the default of the sign-in field.
  static const String defaultEmail = 'demo@example.com';

  /// An identity the mock provider knows but the example never invited.
  static const String notInvitedEmail = 'notinvited@example.com';

  /// How many silent renewals ran since start (or the last [reset]).
  static final ValueNotifier<int> renewals = ValueNotifier<int>(0);

  // On web this client sends cookies to the API origin (see example_http_client_web.dart).
  static http.Client _http = makeExampleHttpClient();
  static _Wiring? _wiring;
  static AuthSession? _session;
  static Future<AuthSession>? _signingIn;

  static _Wiring get _w => _wiring ??= _Wiring(_http, baseUrl);

  /// The shared client; send every authenticated call through it.
  static ApiClient get api => _w.api;

  static InMemoryTokenStore get tokens => _w.tokens;

  /// The mock identity provider behind the e-mail sign-in.
  static FakeIdTokenSource get idSource => _w.source;

  static AuthGateway get demoGateway => _w.demo;

  static AuthGateway get firebaseGateway => _w.firebase;

  /// The session made by the last sign-in, null when signed out.
  static AuthSession? get session => _session;

  static Future<void> _forget() async {
    _session = null;
    await _wiring?.tokens.clear();
  }

  /// Replaces the transport and starts over (tests, or a new base URL).
  static void reset({http.Client? client, Uri? base}) {
    if (client != null) _http = client;
    if (base != null) baseUrl = base;
    _wiring = null;
    _session = null;
    _signingIn = null;
    renewals.value = 0;
  }

  /// Signs in as [defaultUserId] through `POST /auth/demo` unless a session
  /// already exists. Concurrent callers share one request.
  static Future<AuthSession> ensureSignedIn() {
    final existing = _session;
    if (existing != null && tokens.token != null) return Future.value(existing);
    return _signingIn ??= _signInDemo(defaultUserId).whenComplete(() => _signingIn = null);
  }

  static Future<AuthSession> _signInDemo(String userId) async {
    final s = await _w.demo.signInDemo(userId);
    _w.active = _w.demo;
    return _session = s;
  }

  /// Signs in as [userId] with the demo route.
  static Future<AuthSession> signInDemo(String userId) => _signInDemo(userId);

  /// Signs in through the mock identity provider: the id token is
  /// `mock:<email>`. Throws [AuthFailure] (for example `not_invited`).
  static Future<AuthSession> signInWithEmail(String email) async {
    // Only a successful sign-in changes who renews the session: a refused
    // identity (not invited) must not take over the one already signed in.
    try {
      final s = await _w.firebase.signInWithEmail(email, 'mock-password');
      _w.active = _w.firebase;
      return _session = s;
    } catch (_) {
      if (identical(_w.active, _w.demo)) _w.source.token = null;
      rethrow;
    }
  }

  /// Renews the session now, as a 401 would. Null when offline.
  static Future<AuthSession?> refresh() async {
    final s = await _w.active.refreshSession(expectedUserId: _session?.userId);
    if (s != null) _session = s;
    return s;
  }

  /// Ends the session on the server and here.
  static Future<void> signOut() async {
    final active = _w.active;
    _session = null;
    await active.signOut();
  }

  /// `GET /health`, decoded.
  static Future<Map<String, Object?>> health() => api.getJson('/health');
}

class _Wiring {
  _Wiring(http.Client client, Uri base)
      : tokens = InMemoryTokenStore(),
        source = FakeIdTokenSource() {
    api = ApiClient(baseUrl: base, http: client, tokens: tokens, isWeb: kIsWeb);
    demo = DemoAuthGateway(api: api, tokens: tokens);
    firebase = FirebaseAuthGateway(api: api, tokens: tokens, source: source);
    active = demo;
    // A session the server or the provider ended: drop it so nothing keeps
    // answering as the dead one and `ensureSignedIn` signs in afresh.
    api.onSessionExpired = api.onSessionRevoked = api.onDeactivated = DemoSession._forget;
    api.onUnauthorized = () {
      DemoSession.renewals.value++;
      return renewalHook(active, expectedUserId: DemoSession._session?.userId)();
    };
  }

  final InMemoryTokenStore tokens;
  final FakeIdTokenSource source;
  late final ApiClient api;
  late final DemoAuthGateway demo;
  late final FirebaseAuthGateway firebase;
  late AuthGateway active;
}
