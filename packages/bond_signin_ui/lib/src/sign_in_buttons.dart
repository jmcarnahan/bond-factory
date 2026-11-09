import 'package:bond_auth/bond_auth.dart';
import 'dart:async';

import 'package:bond_signin/bond_signin.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/widgets.dart';

/// One button per sign-in provider, stacked. Each is `<prefix>.<provider id>`
/// to a test driver. While [busy] every button is disabled. Nothing here opens
/// a dialog: the browser step is the page's job.
class BondSignInButtons extends StatelessWidget {
  const BondSignInButtons({
    super.key,
    required this.providers,
    required this.labels,
    required this.onStart,
    this.busy = false,
    this.semanticsPrefix = 'sdk.signin',
  });

  final List<SignInProvider> providers;
  final SignInLabels labels;
  final Future<void> Function(String providerId) onStart;
  final bool busy;
  final String semanticsPrefix;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (var i = 0; i < providers.length; i++) ...[
          if (i > 0) BondSpace.h12,
          BondButton(
            label: labels.continueWith(providers[i].label),
            variant: i == 0 ? BondButtonVariant.primary : BondButtonVariant.secondary,
            size: BondButtonSize.large,
            expand: true,
            wrapLabel: true,
            onPressed: busy ? null : () => unawaited(onStart(providers[i].id)),
            semanticsId: '$semanticsPrefix.${providers[i].id}',
          ),
        ],
      ],
    );
  }
}
