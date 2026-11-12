import 'package:bond_auth/bond_auth.dart';
import 'package:bond_signin/bond_signin.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

import 'sign_in_buttons.dart';

/// The sign-in page body: a title, one button per `providers.signin`, the
/// invite-only line, an inline error strip and, when the server allows it and
/// the app supplies one, a link that reveals the administrator sign-in in
/// place. No dialog, no sheet, no route push.
///
/// Semantics ids: `<prefix>.<provider>`, `<prefix>.error`, `<prefix>.break-glass`.
class BondSignInScreen extends StatefulWidget {
  const BondSignInScreen({
    super.key,
    required this.providers,
    required this.labels,
    required this.onStart,
    this.breakGlass,
    this.header,
    this.errorCode,
    this.busy = false,
    this.semanticsPrefix = 'sdk.signin',
  });

  final AuthProviders providers;
  final SignInLabels labels;
  final Future<void> Function(String providerId) onStart;

  /// Builds the administrator sign-in form; shown inline under the link, and
  /// only when `providers.breakGlass` is true.
  final WidgetBuilder? breakGlass;

  /// Logo or app name above the title.
  final Widget? header;

  /// A refusal or session-end code to show (`not_invited`, `refresh_reused`...).
  final String? errorCode;
  final bool busy;
  final String semanticsPrefix;

  @override
  State<BondSignInScreen> createState() => _BondSignInScreenState();
}

class _BondSignInScreenState extends State<BondSignInScreen> {
  bool _breakGlassOpen = false;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final text = BondText(t);
    final w = widget;
    final showBreakGlass = w.providers.breakGlass && w.breakGlass != null;
    final code = w.errorCode;
    return Center(
      child: SingleChildScrollView(
        padding: BondSpace.all16,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: BondLayout.formMaxWidth),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (w.header != null) ...[w.header!, BondSpace.h24],
              Text(w.labels.title, style: text.heading),
              BondSpace.h24,
              if (code != null) ...[_ErrorStrip(message: w.labels.messageFor(code), id: '${w.semanticsPrefix}.error'), BondSpace.h16],
              BondSignInButtons(
                providers: w.providers.signin,
                labels: w.labels,
                onStart: w.onStart,
                busy: w.busy,
                semanticsPrefix: w.semanticsPrefix,
              ),
              if (w.busy) ...[BondSpace.h12, Text(w.labels.working, style: text.small, textAlign: TextAlign.center)],
              BondSpace.h16,
              Text(w.labels.inviteOnly, style: text.small, textAlign: TextAlign.center),
              if (showBreakGlass) ...[
                BondSpace.h16,
                Align(
                  child: BondButton(
                    label: w.labels.breakGlass,
                    variant: BondButtonVariant.quiet,
                    onPressed: () => setState(() => _breakGlassOpen = !_breakGlassOpen),
                    semanticsId: '${w.semanticsPrefix}.break-glass',
                  ),
                ),
                if (_breakGlassOpen) ...[BondSpace.h8, Builder(builder: w.breakGlass!)],
              ],
            ],
          ),
        ),
      ),
    );
  }
}

/// The refusal notice: one live-region semantics node whose label is the
/// message, so a screen reader or a walk reads it once.
class _ErrorStrip extends StatelessWidget {
  const _ErrorStrip({required this.message, required this.id});

  final String message;
  final String id;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final c = t.colorsFor(BondToneRole.danger);
    return Container(
      padding: BondSpace.all16,
      decoration: BoxDecoration(color: c.background, borderRadius: t.shape.r12All, border: Border.all(color: c.border)),
      child: Semantics(
        identifier: id,
        label: message,
        container: true,
        liveRegion: true,
        excludeSemantics: true,
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Icon(Icons.error_outline, size: BondLayout.icon, color: c.foreground),
          BondSpace.w12,
          Expanded(child: Text(message, style: BondText(t).small)),
        ]),
      ),
    );
  }
}
