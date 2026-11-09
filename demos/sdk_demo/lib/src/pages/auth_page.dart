import 'package:bond_api/bond_api.dart';
import 'package:bond_auth/bond_auth.dart';
import 'package:flutter/material.dart';

import '../example_api.dart';
import 'page_scaffold.dart';

/// Sign in (mock identity provider or demo route), read the session, renew it,
/// force a 401 and watch one renewal, hit the not-invited refusal, sign out.
/// Everything shows inline; ids are `sdk.auth.<element>`.
class AuthPage extends StatefulWidget {
  const AuthPage({super.key});

  @override
  State<AuthPage> createState() => _AuthPageState();
}

class _AuthPageState extends State<AuthPage> {
  final _email = TextEditingController(text: DemoSession.defaultEmail);
  AuthSession? _session = DemoSession.session;
  AuthFailure? _error;
  String? _refreshResult;
  String? _force401Result;
  bool _busy = false;

  @override
  void dispose() {
    _email.dispose();
    super.dispose();
  }

  Future<void> _run(Future<void> Function() action) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action();
    } on AuthFailure catch (e) {
      if (mounted) setState(() => _error = e);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = AuthFailure.fromApi(e));
    } finally {
      // The shared session may have ended while the call ran (a refused renewal).
      if (mounted) {
        setState(() {
          _busy = false;
          _session = DemoSession.session;
        });
      }
    }
  }

  Future<void> _signIn(String email) => _run(() async {
        final s = await DemoSession.signInWithEmail(email.trim());
        if (mounted) setState(() => _session = s);
      });

  Future<void> _signInDemo() => _run(() async {
        final s = await DemoSession.signInDemo(DemoSession.defaultUserId);
        if (mounted) setState(() => _session = s);
      });

  Future<void> _refresh() => _run(() async {
        final s = await DemoSession.refresh();
        if (!mounted) return;
        setState(() {
          _session = s ?? _session;
          _refreshResult = s == null ? 'Offline: the session was kept' : 'Renewed: token ends ${_tail(s.token)}';
        });
      });

  /// Puts a token the server rejects in the store, then makes one ordinary call.
  /// The client renews once and replays it.
  Future<void> _force401() => _run(() async {
        final before = DemoSession.renewals.value;
        DemoSession.tokens.token = 'broken.token.value';
        final me = await DemoSession.api.getJson('/auth/me');
        final user = me['user'];
        final email = user is Map ? user['email'] : null;
        final n = DemoSession.renewals.value - before;
        if (!mounted) return;
        setState(() => _force401Result = '$n renewal, request succeeded as $email');
      });

  Future<void> _signOut() => _run(() async {
        await DemoSession.signOut();
        if (!mounted) return;
        setState(() {
          _session = null;
          _refreshResult = null;
          _force401Result = null;
        });
      });

  static String _tail(String token) => token.length <= 6 ? token : token.substring(token.length - 6);

  @override
  Widget build(BuildContext context) {
    final session = _session;
    return PageFrame(
      title: 'Auth',
      children: [
        Semantics(
          identifier: 'sdk.auth.email',
          label: 'E-mail',
          child: TextField(
            controller: _email,
            decoration: const InputDecoration(labelText: 'E-mail (mock identity provider)'),
            keyboardType: TextInputType.emailAddress,
          ),
        ),
        const SizedBox(height: 12),
        Wrap(spacing: 8, runSpacing: 8, children: [
          _button('sign-in', 'Sign in', () => _signIn(_email.text), filled: true),
          _button('sign-in-demo', 'Sign in as demo user', _signInDemo),
          _button('not-invited', 'Sign in as not-invited identity', () => _signIn(DemoSession.notInvitedEmail)),
        ]),
        if (_error != null) _ErrorLine(_error!),
        const SizedBox(height: 16),
        if (session == null)
          Semantics(identifier: 'sdk.auth.signed-out', child: const Text('Signed out')) else ..._signedIn(session),
      ],
    );
  }

  List<Widget> _signedIn(AuthSession session) {
    final name = jsonText(session.user['name']) ?? session.userId;
    final email = jsonText(session.user['email']);
    return [
      Semantics(
        identifier: 'sdk.auth.user',
        child: Text(email == null ? name : '$name ($email)', style: Theme.of(context).textTheme.titleMedium),
      ),
      const SizedBox(height: 8),
      Semantics(
        identifier: 'sdk.auth.capabilities',
        child: Wrap(spacing: 6, runSpacing: 6, children: [
          for (final c in session.capabilities) Chip(label: Text(c)),
          if (session.capabilities.isEmpty) const Text('No capabilities'),
        ]),
      ),
      const SizedBox(height: 8),
      Semantics(
        identifier: 'sdk.auth.token-tail',
        child: Text('Token ends ${_tail(DemoSession.tokens.token ?? session.token)}'),
      ),
      const SizedBox(height: 12),
      Wrap(spacing: 8, runSpacing: 8, children: [
        _button('refresh', 'Refresh session', _refresh),
        _button('force-401', 'Force a 401', _force401),
        _button('sign-out', 'Sign out', _signOut),
      ]),
      if (_refreshResult != null)
        Semantics(identifier: 'sdk.auth.refresh-result', child: Text(_refreshResult!)),
      if (_force401Result != null)
        Semantics(identifier: 'sdk.auth.force-401-result', child: Text(_force401Result!)),
      ValueListenableBuilder<int>(
        valueListenable: DemoSession.renewals,
        builder: (_, n, _) => Semantics(identifier: 'sdk.auth.renewals', child: Text('Renewals: $n')),
      ),
    ];
  }

  Widget _button(String id, String label, VoidCallback onPressed, {bool filled = false}) {
    final tap = _busy ? null : onPressed;
    return Semantics(
      identifier: 'sdk.auth.$id',
      label: label,
      child: filled ? FilledButton(onPressed: tap, child: Text(label)) : OutlinedButton(onPressed: tap, child: Text(label)),
    );
  }
}

/// A JSON value as text, null when it is absent or empty.
String? jsonText(Object? v) {
  final s = v?.toString();
  return s == null || s.isEmpty ? null : s;
}

class _ErrorLine extends StatelessWidget {
  const _ErrorLine(this.failure);

  final AuthFailure failure;

  @override
  Widget build(BuildContext context) {
    final parts = [
      'code: ${failure.code ?? failure.reason.name}',
      if (failure.message != null) 'message: ${failure.message}',
      if (failure.hint != null) 'hint: ${failure.hint}',
    ];
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: Semantics(
        identifier: 'sdk.auth.error',
        child: Text(parts.join(' | '), style: TextStyle(color: Theme.of(context).colorScheme.error)),
      ),
    );
  }
}
