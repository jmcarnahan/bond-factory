import 'package:bond_api/bond_api.dart';
import 'package:bond_auth/bond_auth.dart';
import 'package:flutter/material.dart';

import '../example_api.dart';
import 'auth_widgets.dart';

/// The administrator form, shown inline only when the server's providers say
/// `break_glass`: e-mail through the mock identity provider, or the demo route.
class BreakGlassForm extends StatefulWidget {
  const BreakGlassForm({super.key, required this.onSignedIn});

  final ValueChanged<AuthSession> onSignedIn;

  @override
  State<BreakGlassForm> createState() => _BreakGlassFormState();
}

class _BreakGlassFormState extends State<BreakGlassForm> {
  final _email = TextEditingController(text: DemoSession.defaultEmail);
  AuthFailure? _error;
  bool _busy = false;

  @override
  void dispose() {
    _email.dispose();
    super.dispose();
  }

  Future<void> _run(Future<AuthSession> Function() action) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final s = await action();
      if (mounted) widget.onSignedIn(s);
    } on AuthFailure catch (e) {
      if (mounted) setState(() => _error = e);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = AuthFailure.fromApi(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final tap = _busy ? null : (Future<AuthSession> Function() a) => _run(a);
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
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
        authButton('sign-in', 'Sign in', tap == null ? null : () => tap(() => DemoSession.signInWithEmail(_email.text.trim())), filled: true),
        authButton('sign-in-demo', 'Sign in as demo user',
            tap == null ? null : () => tap(() => DemoSession.signInDemo(DemoSession.defaultUserId))),
        authButton('not-invited', 'Sign in as not-invited identity',
            tap == null ? null : () => tap(() => DemoSession.signInWithEmail(DemoSession.notInvitedEmail))),
      ]),
      if (_error != null) AuthErrorLine(_error!),
    ]);
  }
}
