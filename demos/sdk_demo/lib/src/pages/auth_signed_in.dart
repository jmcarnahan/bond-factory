import 'package:bond_api/bond_api.dart';
import 'package:bond_auth/bond_auth.dart';
import 'package:flutter/material.dart';

import '../example_api.dart';
import 'auth_widgets.dart';

/// What a signed-in session shows: claims chips, then renew, force a 401,
/// replay a used refresh token, sign out. Everything inline.
class AuthSignedIn extends StatefulWidget {
  const AuthSignedIn({super.key, required this.session, required this.onChanged});

  final AuthSession session;

  /// The shared session changed (renewed, ended, signed out): read it again.
  final VoidCallback onChanged;

  @override
  State<AuthSignedIn> createState() => _AuthSignedInState();
}

class _AuthSignedInState extends State<AuthSignedIn> {
  AuthFailure? _error;
  String? _refreshResult;
  String? _force401Result;
  bool _busy = false;

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
      if (mounted) setState(() => _busy = false);
      // The shared session may have ended while the call ran (a refused renewal).
      widget.onChanged();
    }
  }

  Future<void> _refresh() => _run(() async {
        final s = await DemoSession.refresh();
        if (!mounted) return;
        setState(() {
          _refreshResult = s == null ? 'Offline: the session was kept' : 'Refreshed: token ends ${tokenTail(s.token)}';
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

  Future<void> _simulateReuse() => _run(DemoSession.simulateReuse);

  Future<void> _signOut() => _run(DemoSession.signOut);

  @override
  Widget build(BuildContext context) {
    final session = widget.session;
    final name = jsonText(session.user['name']) ?? session.userId;
    final email = jsonText(session.user['email']);
    final who = email == null ? name : '$name ($email)';
    final tail = 'Token ends ${tokenTail(DemoSession.tokens.token ?? session.token)}';
    final tap = _busy ? null : (Future<void> Function() a) => a();
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      authRead('user', who, Text(who, style: Theme.of(context).textTheme.titleMedium)),
      const SizedBox(height: 8),
      authRead(
        'capabilities',
        session.capabilities.isEmpty ? 'No capabilities' : 'Capabilities: ${session.capabilities.join(', ')}',
        Wrap(spacing: 6, runSpacing: 6, children: [
          for (final c in session.capabilities) Chip(label: Text(c)),
          if (session.capabilities.isEmpty) const Text('No capabilities'),
        ]),
      ),
      const SizedBox(height: 8),
      authRead('token-tail', tail, Text(tail)),
      const SizedBox(height: 12),
      Wrap(spacing: 8, runSpacing: 8, children: [
        authButton('refresh', 'Refresh session', tap == null ? null : () => tap(_refresh)),
        authButton('force-401', 'Force a 401', tap == null ? null : () => tap(_force401)),
        authButton('simulate-reuse', 'Simulate refresh-token reuse', tap == null ? null : () => tap(_simulateReuse)),
        authButton('sign-out', 'Sign out', tap == null ? null : () => tap(_signOut)),
      ]),
      if (_error != null) AuthErrorLine(_error!),
      if (_refreshResult != null) authRead('refresh-result', _refreshResult!, Text(_refreshResult!)),
      if (_force401Result != null) authRead('force-401-result', _force401Result!, Text(_force401Result!)),
      ValueListenableBuilder<int>(
        valueListenable: DemoSession.renewals,
        builder: (_, n, _) => authRead('renewals', 'Renewals: $n', Text('Renewals: $n')),
      ),
    ]);
  }
}
