import 'package:flutter/material.dart';

import '../primitives/bond_button.dart';
import '../primitives/bond_text_field.dart';
import '../tokens/tokens.dart';
import '../labels.dart';

/// E-mail and password sign-in with "Forgot password?", all inline.
///
/// Callbacks only: this form owns the fields and their inline validation (an
/// empty or malformed e-mail, an empty password) and calls [onSignIn] with the
/// trimmed e-mail and the password once both look usable. The page owns the
/// auth call, and shows its result through [errorText] (a failed sign-in) and
/// [noticeText] (the outcome of a password reset), both written by the page.
class BondEmailSignIn extends StatefulWidget {
  const BondEmailSignIn({
    super.key,
    required this.onSignIn,
    this.onForgot,
    this.busy = false,
    this.errorText,
    this.noticeText,
    this.semanticsId = 'login',
  });

  final void Function(String email, String password) onSignIn;

  /// Called with the trimmed e-mail when it is valid. Null hides the link.
  final void Function(String email)? onForgot;
  final bool busy;
  final String? errorText;
  final String? noticeText;

  /// Prefix: `<id>-email`, `<id>-password`, `<id>-submit`, `<id>-forgot`.
  final String? semanticsId;

  @override
  State<BondEmailSignIn> createState() => _BondEmailSignInState();
}

class _BondEmailSignInState extends State<BondEmailSignIn> {
  final _email = TextEditingController();
  final _password = TextEditingController();
  String? _emailError;
  String? _passwordError;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  String? _id(String part) => widget.semanticsId == null ? null : '${widget.semanticsId}-$part';

  static bool _looksLikeEmail(String s) => RegExp(r'^[^\s@]+@[^\s@]+\.[^\s@]+$').hasMatch(s);

  String? _checkEmail() {
    final email = _email.text.trim();
    if (email.isEmpty) return BondLabels.of(context).emailRequired;
    if (!_looksLikeEmail(email)) return BondLabels.of(context).emailInvalid;
    return null;
  }

  void _submit() {
    if (widget.busy) return;
    final e = _checkEmail();
    final p = _password.text.isEmpty ? BondLabels.of(context).passwordRequired : null;
    setState(() {
      _emailError = e;
      _passwordError = p;
    });
    if (e == null && p == null) widget.onSignIn(_email.text.trim(), _password.text);
  }

  void _forgot() {
    final e = _checkEmail();
    setState(() {
      _emailError = e == BondLabels.of(context).emailRequired ? BondLabels.of(context).resetNeedsEmail : e;
      _passwordError = null;
    });
    if (e == null) widget.onForgot!(_email.text.trim());
  }

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final text = BondText(t);
    final l = BondLabels.of(context);
    return AutofillGroup(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          BondTextField(
            key: const ValueKey('bond-login-email'),
            controller: _email,
            label: l.emailLabel,
            errorText: _emailError,
            enabled: !widget.busy,
            keyboardType: TextInputType.emailAddress,
            autofillHints: const [AutofillHints.email],
            textInputAction: TextInputAction.next,
            semanticsId: _id('email'),
            onChanged: (_) {
              if (_emailError != null) setState(() => _emailError = null);
            },
          ),
          BondSpace.h12,
          BondTextField(
            key: const ValueKey('bond-login-password'),
            controller: _password,
            label: l.passwordLabel,
            errorText: _passwordError,
            enabled: !widget.busy,
            obscureText: true,
            autofillHints: const [AutofillHints.password],
            textInputAction: TextInputAction.done,
            semanticsId: _id('password'),
            onChanged: (_) {
              if (_passwordError != null) setState(() => _passwordError = null);
            },
            onSubmitted: (_) => _submit(),
          ),
          if (widget.errorText != null) ...[
            BondSpace.h12,
            Semantics(
              identifier: _id('error'),
              liveRegion: true,
              child: Text(widget.errorText!,
                  key: const ValueKey('bond-login-error'),
                  style: text.style(BondText.small14, BondText.medium, color: t.danger.press)),
            ),
          ],
          BondSpace.h16,
          BondButton(
            key: const ValueKey('bond-login-submit'),
            label: l.signIn,
            size: BondButtonSize.large,
            loading: widget.busy,
            onPressed: _submit,
            semanticsId: _id('submit'),
          ),
          if (widget.onForgot != null) ...[
            BondSpace.h8,
            Align(
              alignment: Alignment.centerLeft,
              child: BondButton(
                key: const ValueKey('bond-login-forgot'),
                label: l.forgotPassword,
                variant: BondButtonVariant.quiet,
                onPressed: widget.busy ? null : _forgot,
                semanticsId: _id('forgot'),
              ),
            ),
          ],
          if (widget.noticeText != null)
            Padding(
              padding: const EdgeInsets.only(top: BondSpace.s8),
              child: Semantics(
                identifier: _id('notice'),
                liveRegion: true,
                child: Text(widget.noticeText!,
                    key: const ValueKey('bond-login-notice'),
                    style: text.style(BondText.small14, BondText.medium, color: t.positive.press)),
              ),
            ),
        ],
      ),
    );
  }
}
