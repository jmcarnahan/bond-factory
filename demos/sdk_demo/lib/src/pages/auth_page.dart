import 'package:bond_api/bond_api.dart';
import 'package:bond_auth/bond_auth.dart';
import 'package:bond_signin/bond_signin.dart';
import 'package:bond_signin_ui/bond_signin_ui.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../example_api.dart';
import 'auth_break_glass.dart';
import 'auth_signed_in.dart';
import 'auth_widgets.dart';
import 'page_scaffold.dart';

export 'auth_widgets.dart' show jsonText;

const _labels = SignInLabels();

/// Direct sign-in against the example's fake providers: a button per provider
/// leaves for the fake consent page and comes back to `/auth?signin=ok|error`.
/// Signed in, the page shows the claims, renews, replays a used refresh token
/// and signs out. Everything shows inline; ids are `sdk.signin.<element>` for
/// the sign-in screen and `sdk.auth.<element>` for the rest.
class AuthPage extends StatefulWidget {
  const AuthPage({super.key, this.currentUrl, this.replaceUrl, this.restoreSession});

  /// The address the page was opened with; defaults to the browser's.
  final Uri? currentUrl;

  /// Puts the cleaned address (return parameters removed) in the address bar.
  /// Defaults to `history.replaceState` on web and nothing elsewhere.
  final void Function(Uri url)? replaceUrl;

  /// Whether to pick up a cookie session on load; defaults to web only.
  final bool? restoreSession;

  @override
  State<AuthPage> createState() => _AuthPageState();
}

class _AuthPageState extends State<AuthPage> {
  AuthSession? _session = DemoSession.session;
  AuthProviders? _providers;
  AuthFailure? _loadError;
  String? _returnReason;
  bool _starting = false;

  Uri get _here => widget.currentUrl ?? Uri.base;

  @override
  void initState() {
    super.initState();
    _start();
  }

  Future<void> _start() async {
    final back = SignInReturn.parse(_here);
    if (back.kind != SignInReturnKind.none) _clean();
    if (back.kind == SignInReturnKind.error) _returnReason = back.reason;
    final restore = widget.restoreSession ?? kIsWeb;
    if (_session == null && (back.kind == SignInReturnKind.ok || restore)) {
      try {
        final s = await DemoSession.completeWeb();
        if (mounted) setState(() => _session = s);
      } on AuthFailure catch (e) {
        // A return that says ok but cannot be completed is shown; a plain visit is just signed out.
        if (back.kind == SignInReturnKind.ok && mounted) setState(() => _returnReason = e.code ?? 'unknown');
      } on ApiException catch (e) {
        if (back.kind == SignInReturnKind.ok && mounted) setState(() => _returnReason = AuthFailure.fromApi(e).code ?? 'unknown');
      }
    }
    await _loadProviders();
  }

  /// Takes the return parameters out of the address bar so a reload cannot replay them.
  void _clean() {
    final cleaned = SignInReturn.cleaned(_here);
    final custom = widget.replaceUrl;
    if (custom != null) {
      custom(cleaned);
    } else {
      replaceAddress(cleaned);
    }
  }

  Future<void> _loadProviders() async {
    try {
      final p = await DemoSession.providers();
      if (mounted) setState(() => _providers = p);
    } on AuthFailure catch (e) {
      if (mounted) setState(() => _loadError = e);
    } on ApiException catch (e) {
      if (mounted) setState(() => _loadError = AuthFailure.fromApi(e));
    }
  }

  Future<void> _signInWith(String providerId) async {
    setState(() {
      _starting = true;
      _returnReason = null;
      _loadError = null;
    });
    try {
      await DemoSession.signInWith(providerId, origin: widget.currentUrl);
    } on AuthFailure catch (e) {
      if (mounted) setState(() => _loadError = e);
    } on ApiException catch (e) {
      if (mounted) setState(() => _loadError = AuthFailure.fromApi(e));
    } finally {
      if (mounted) setState(() => _starting = false);
    }
  }

  void _changed() {
    if (mounted) setState(() => _session = DemoSession.session);
  }

  @override
  Widget build(BuildContext context) {
    final session = _session;
    final providers = _providers;
    return PageFrame(
      title: 'Auth',
      children: [
        ValueListenableBuilder<String?>(
          valueListenable: DemoSession.endedReason,
          builder: (_, code, _) {
            if (code == null || session != null) return const SizedBox.shrink();
            final text = _labels.messageFor(code);
            return Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: authRead('ended', text, Text(text, style: TextStyle(color: Theme.of(context).colorScheme.error))),
            );
          },
        ),
        if (session != null)
          AuthSignedIn(session: session, onChanged: _changed)
        else ...[
          authRead('signed-out', 'Signed out', const Text('Signed out')),
          const SizedBox(height: 8),
          if (providers != null)
            BondSignInScreen(
              providers: providers,
              labels: _labels,
              onStart: _signInWith,
              busy: _starting,
              errorCode: _returnReason,
              breakGlass: (_) => BreakGlassForm(onSignedIn: (s) => setState(() => _session = s)),
            ),
          if (_loadError != null) AuthErrorLine(_loadError!),
          if (providers == null && _loadError == null)
            authRead('loading', 'Loading sign-in options...', const Text('Loading sign-in options...')),
        ],
      ],
    );
  }
}
