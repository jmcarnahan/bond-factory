import 'dart:async';

import 'package:bond_api/bond_api.dart';
import 'package:bond_auth/bond_auth.dart';
import 'package:bond_signin/bond_signin.dart';
import 'package:bond_signin_ui/bond_signin_ui.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'example_http_client_io.dart' if (dart.library.js_interop) 'example_http_client_web.dart';

/// The one session every demo page shares: a single [ApiClient] whose bearer
/// token lives in an [InMemoryTokenStore] and whose 401 renewal goes through
/// the gateway the person signed in with.
///
/// The example runs in fake mode. Direct sign-in goes through the example's fake
/// providers and its consent page ([OidcAuthGateway]); the break-glass e-mail
/// form uses a [FakeIdTokenSource] whose id tokens read `mock:<email>`.
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

  /// The server's code when a renewal ended the session for good (for example
  /// `refresh_reused`); the auth page words it inline. Cleared by a sign-in.
  static final ValueNotifier<String?> endedReason = ValueNotifier<String?>(null);

  /// The system-browser port; tests replace it. On web this navigates the window.
  static BrowserAuth Function() browserAuth = defaultBrowserAuth;

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

  /// The direct sign-in gateway (cookie delivery on web).
  static OidcAuthGateway get oidc => _w.oidc;

  static AuthGateway get demoGateway => _w.demo;

  static AuthGateway get firebaseGateway => _w.firebase;

  /// The session made by the last sign-in, null when signed out.
  static AuthSession? get session => _session;

  static Future<void> _forget() async {
    _setSession(null);
    await _wiring?.tokens.clear();
  }

  /// Replaces the transport and starts over (tests, or a new base URL).
  static void reset({http.Client? client, Uri? base}) {
    if (client != null) _http = client;
    if (base != null) baseUrl = base;
    _wiring = null;
    _setSession(null);
    _signingIn = null;
    renewals.value = 0;
    endedReason.value = null;
    useCookieSession = kIsWeb;
  }

  /// Uses the session that exists. Otherwise, on web, picks up a cookie session
  /// ([completeWeb]); failing that signs in as [defaultUserId] through
  /// `POST /auth/demo`. Concurrent callers share one request.
  static Future<AuthSession> ensureSignedIn() {
    final existing = _session;
    if (existing != null && tokens.token != null) return Future.value(existing);
    return _signingIn ??= _establish().whenComplete(() => _signingIn = null);
  }

  /// The one place `_session` changes. When the person (user id) changes, the stop hooks run for the
  /// one who left and the start hooks for the one who arrived, so the alerts always follow the
  /// session: a server-ended session, a switch of user and a reset all stop them. Hooks are not awaited
  /// (a hook must never fail a sign-in); `TodoAlerts` serialises them.
  static void _setSession(AuthSession? s) {
    _session = s;
    final uid = s?.userId;
    if (uid == _hooked) return;
    final had = _hooked != null;
    _hooked = uid;
    if (had) unawaited(_runHooks(signOutHooks));
    if (uid != null) unawaited(_runHooks(signInHooks));
  }

  /// The user id the start hooks last ran for; null when none.
  static String? _hooked;

  static Future<void> _runHooks(List<Future<void> Function()> hooks) async {
    for (final hook in List.of(hooks)) {
      try {
        await hook();
      } catch (_) {
        // A hook (the alerts) must never fail a sign-in or a sign-out.
      }
    }
  }

  /// Run after each successful sign-in (the alerts coordinator starts here); `main()` adds them.
  static final List<Future<void> Function()> signInHooks = [];

  /// Run when the person signs out (the alerts coordinator stops here).
  static final List<Future<void> Function()> signOutHooks = [];

  /// Whether [ensureSignedIn] first tries the cookie session; web only (tests flip it).
  static bool useCookieSession = kIsWeb;

  /// Codes that mean a session existed and was ended: never answered by a demo sign-in.
  static const Set<String> _endedCodes = {
    'refresh_reused',
    'refresh_expired',
    'refresh_revoked',
    'session_revoked',
    'deactivated',
    'not_invited',
  };

  static Future<AuthSession> _establish() async {
    if (useCookieSession) {
      try {
        return await completeWeb();
      } on Object catch (e) {
        final code = switch (e) {
          AuthFailure() => e.code,
          ApiException() => AuthFailure.fromApi(e).code,
          _ => null,
        };
        if (code != null && _endedCodes.contains(code)) {
          // An ended session shows as such; it must not turn into the demo user.
          endedReason.value = code;
          rethrow;
        }
        // No cookie session (or no answer): fall back to the demo route below.
      }
    }
    return _signInDemo(defaultUserId);
  }

  /// Web: asks the server for the access token of the cookie session
  /// (`POST /auth/refresh` with `{}`), after a return with `signin=ok` or a reload.
  static Future<AuthSession> completeWeb() async {
    final s = await _w.oidc.completeWeb();
    _w.active = _w.oidc;
    endedReason.value = null;
    _setSession(s);
    return s;
  }

  /// The sign-in providers the example offers (`GET /auth/providers`).
  static Future<AuthProviders> providers() => _w.oidc.providers();

  /// Starts direct sign-in with [providerId]: the server answers the provider's
  /// address and the system browser goes there. On web the window leaves the
  /// app and the next load shows the result (`?signin=ok|error`).
  static Future<void> signInWith(String providerId, {Uri? origin}) async {
    final here = origin ?? Uri.base;
    final back = '${here.origin}/auth';
    final url = await SignInApi(api).startWeb(providerId, redirectTo: back);
    await browserAuth().run(url, callback: Uri.parse(back));
  }

  /// Fake mode only: the server replays an already-rotated refresh token
  /// (`POST /auth/simulate-reuse`), then the client renews once. The session
  /// must end with `refresh_reused`, which lands in [endedReason].
  static Future<void> simulateReuse() async {
    String? code;
    try {
      await api.postJson('/auth/simulate-reuse');
    } on ApiException catch (e) {
      code = AuthFailure.fromApi(e).code;
    } on AuthFailure catch (e) {
      code = e.code;
    }
    try {
      await _w.active.refreshSession(expectedUserId: _session?.userId);
    } on AuthFailure {
      // The expected end: the gateway already recorded the code.
    }
    if (code == 'refresh_reused') {
      // The reuse itself is the reason, whatever word the follow-up renewal got.
      await _forget();
      endedReason.value = code;
    }
  }

  static Future<AuthSession> _signInDemo(String userId) async {
    final s = await _w.demo.signInDemo(userId);
    _w.active = _w.demo;
    endedReason.value = null;
    _setSession(s);
    return s;
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
      endedReason.value = null;
      _setSession(s);
      return s;
    } catch (_) {
      if (identical(_w.active, _w.demo)) _w.source.token = null;
      rethrow;
    }
  }

  /// Renews the session now, as a 401 would. Null when offline.
  static Future<AuthSession?> refresh() async {
    final s = await _w.active.refreshSession(expectedUserId: _session?.userId);
    if (s != null) _setSession(s);
    return s;
  }

  /// Ends the session on the server and here.
  static Future<void> signOut() async {
    final active = _w.active;
    // Stop the alerts while the token still works (push unregisters over the API), then end the session.
    if (_hooked != null) {
      _hooked = null;
      await _runHooks(signOutHooks);
    }
    _setSession(null);
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
    // Web: the HttpOnly cookie carries the refresh token. Elsewhere (tests) memory does.
    oidc = OidcAuthGateway(
      api: api,
      tokens: tokens,
      refreshTokens: kIsWeb ? const NoRefreshTokenStore() : InMemoryRefreshTokenStore(),
    )..onSessionEnded = (code) {
        DemoSession._setSession(null);
        DemoSession.endedReason.value = code;
      };
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
  late final OidcAuthGateway oidc;
  late final DemoAuthGateway demo;
  late final FirebaseAuthGateway firebase;
  late AuthGateway active;
}
