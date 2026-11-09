import 'package:bond_auth/bond_auth.dart';
import 'package:flutter/material.dart';

/// A read-only value a walk must be able to read: the identifier AND the
/// visible text as the label (the inner text is hidden so it is not doubled).
Widget authRead(String id, String text, Widget child) => Semantics(
      identifier: 'sdk.auth.$id',
      label: text,
      container: true, // its own node: never merged into a neighbour's label
      child: ExcludeSemantics(child: child),
    );

/// An action with an `sdk.auth.<id>` identifier; null [onPressed] disables it.
Widget authButton(String id, String label, VoidCallback? onPressed, {bool filled = false}) => Semantics(
      identifier: 'sdk.auth.$id',
      label: label,
      child: filled
          ? FilledButton(onPressed: onPressed, child: Text(label))
          : OutlinedButton(onPressed: onPressed, child: Text(label)),
    );

/// A JSON value as text, null when it is absent or empty.
String? jsonText(Object? v) {
  final s = v?.toString();
  return s == null || s.isEmpty ? null : s;
}

/// The last six characters of a token: enough to see a renewal, never the token.
String tokenTail(String token) => token.length <= 6 ? token : token.substring(token.length - 6);

/// A refusal as one inline line: code, message, hint.
class AuthErrorLine extends StatelessWidget {
  const AuthErrorLine(this.failure, {super.key});

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
      child: authRead(
        'error',
        parts.join(' | '),
        Text(parts.join(' | '), style: TextStyle(color: Theme.of(context).colorScheme.error)),
      ),
    );
  }
}
