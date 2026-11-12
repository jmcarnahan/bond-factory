import 'package:flutter/material.dart';

import '../labels.dart';
import '../semantics.dart';
import '../tokens/tokens.dart';
import 'bond_button.dart';
import 'bond_icon_button.dart';

/// An inline notice that sits in the page flow.
class BondBanner extends StatelessWidget {
  const BondBanner({
    super.key,
    required this.title,
    this.message,
    this.tone = BondToneRole.info,
    this.icon,
    this.actionLabel,
    this.onAction,
    this.onDismiss,
    this.dismissLabel,
    this.stackAction = false,
    this.semanticsId,
  });

  final String title;
  final String? message;

  /// Null is neutral.
  final BondToneRole? tone;
  final IconData? icon;
  final String? actionLabel;
  final VoidCallback? onAction;
  final VoidCallback? onDismiss;
  final String? dismissLabel;

  /// Puts the action under the text instead of beside it (narrow phone
  /// screens). It also goes under at large text sizes.
  final bool stackAction;
  final String? semanticsId;

  IconData get _defaultIcon => switch (tone) {
        BondToneRole.danger => Icons.error_outline,
        BondToneRole.caution => Icons.warning_amber_rounded,
        BondToneRole.positive => Icons.check_circle_outline,
        _ => Icons.info_outline,
      };

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final text = BondText(t);
    final c = t.colorsFor(tone);
    // Beside the text only while it fits: at large text sizes the action goes
    // under it, or the row would overflow.
    final stacked = stackAction ||
        MediaQuery.textScalerOf(context).scale(BondText.base16) >
            BondText.base16 * 1.25;
    final action = actionLabel == null
        ? null
        : BondButton(
            label: actionLabel!,
            variant: BondButtonVariant.secondary,
            onPressed: onAction,
            semanticsId: semanticsId == null ? null : '$semanticsId-action',
          );
    return bondSemantics(
      id: semanticsId,
      // The action and dismiss buttons stay their own nodes so they can be
      // activated; the text below is the live region.
      explicitChildNodes: true,
      child: Container(
        padding: BondSpace.all16,
        decoration: BoxDecoration(
          color: c.background,
          borderRadius: t.shape.r12All,
          border: Border.all(color: c.border),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon ?? _defaultIcon,
                size: BondLayout.icon, color: c.foreground),
            BondSpace.w12,
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Announced when it appears or changes.
                  Semantics(
                    container: true,
                    liveRegion: true,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(title,
                            style: text.style(
                                BondText.base16, BondText.semibold,
                                color: tone == null ? t.ink : c.foreground)),
                        if (message != null) Text(message!, style: text.small),
                      ],
                    ),
                  ),
                  if (action != null && stacked) ...[BondSpace.h12, action],
                ],
              ),
            ),
            if (action != null && !stacked) ...[BondSpace.w12, action],
            if (onDismiss != null)
              BondIconButton(
                icon: Icons.close,
                label: dismissLabel ?? BondLabels.of(context).dismiss,
                onPressed: onDismiss,
                color: c.foreground,
                semanticsId: semanticsId == null ? null : '$semanticsId-dismiss',
              ),
          ],
        ),
      ),
    );
  }
}
