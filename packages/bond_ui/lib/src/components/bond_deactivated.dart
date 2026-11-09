import 'package:flutter/material.dart';

import '../primitives/bond_button.dart';
import '../tokens/tokens.dart';

/// The whole-screen message for a deactivated account: no navigation, one way
/// out. It sits in the page flow like every other state (no dialog).
///
/// [note] is an optional line under the body ("2 changes not sent") and
/// [extra] an optional inline control under the sign-out button.
class BondDeactivated extends StatelessWidget {
  const BondDeactivated({
    super.key,
    required this.title,
    required this.body,
    required this.signOutLabel,
    required this.onSignOut,
    this.note,
    this.extra,
    this.signOutSemanticsId,
  });

  final String title;
  final String body;
  final String signOutLabel;
  final VoidCallback onSignOut;
  final String? note;
  final Widget? extra;
  final String? signOutSemanticsId;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final text = BondText(t);
    return Scaffold(
      backgroundColor: t.surface,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: BondSpace.all24,
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Icon(Icons.block, size: BondSpace.s48, color: t.danger.base),
                  BondSpace.h16,
                  Semantics(
                    liveRegion: true,
                    child: Text(title, style: text.title, textAlign: TextAlign.center),
                  ),
                  BondSpace.h8,
                  Text(body, style: text.body, textAlign: TextAlign.center),
                  if (note != null) ...[
                    BondSpace.h8,
                    Text(note!, key: const ValueKey('bond-deactivated-note'), style: text.body, textAlign: TextAlign.center),
                  ],
                  BondSpace.h24,
                  BondButton(
                    key: const ValueKey('bond-deactivated-sign-out'),
                    label: signOutLabel,
                    variant: BondButtonVariant.secondary,
                    onPressed: onSignOut,
                    semanticsId: signOutSemanticsId,
                  ),
                  if (extra != null) ...[BondSpace.h16, extra!],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
