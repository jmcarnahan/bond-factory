import 'package:flutter/material.dart';

import '../tokens/tokens.dart';
import 'bond_banner.dart';
import 'bond_button.dart';

/// One "needs you" item: icon, title, context, optional due badge and a
/// single action button. Anything the row grows into (an inline chip row, a
/// date field, a confirm, the result line, an error) renders under it,
/// indented to the title.
class BondActionRow extends StatelessWidget {
  const BondActionRow({
    super.key,
    required this.icon,
    required this.title,
    this.contextText,
    this.actionLabel,
    this.onAction,
    this.dueBadge,
    this.busy = false,
    this.expansion,
    this.result,
    this.error,
    this.iconTone,
    this.trailing,
    this.semanticsId,
  });

  final IconData icon;
  final String title;

  /// The line under the title ("Notified 5:00 PM yesterday.").
  final String? contextText;
  final String? actionLabel;
  final VoidCallback? onAction;
  final Widget? dueBadge;
  final bool busy;

  /// Inline content that opens under the row.
  final Widget? expansion;

  /// The result line after the action ran.
  final Widget? result;

  /// Why the action failed; shown as a danger banner under the row.
  final String? error;

  /// Null is neutral.
  final BondToneRole? iconTone;

  /// Replaces the action button (an inline confirm, say).
  final Widget? trailing;

  /// Identifier of the action button.
  final String? semanticsId;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final text = BondText(t);
    final c = t.colorsFor(iconTone);
    final lane = BondLayout.leadingLane + BondSpace.s12;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: BondSpace.s12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: BondLayout.leadingLane,
                height: BondLayout.leadingLane,
                decoration: BoxDecoration(
                  color: iconTone == null ? t.ground : c.background,
                  shape: BoxShape.circle,
                ),
                child: Icon(icon,
                    size: BondLayout.icon,
                    color: iconTone == null ? t.ink : c.foreground),
              ),
              BondSpace.w12,
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Wrap(
                      crossAxisAlignment: WrapCrossAlignment.center,
                      spacing: BondSpace.s8,
                      children: [
                        Text(title,
                            style: text.style(
                                BondText.base16, BondText.semibold)),
                        ?dueBadge,
                      ],
                    ),
                    if (contextText != null)
                      Text(contextText!, style: text.small),
                  ],
                ),
              ),
              if (trailing != null) ...[BondSpace.w12, trailing!]
              else if (actionLabel != null) ...[
                BondSpace.w12,
                BondButton(
                  label: actionLabel!,
                  variant: BondButtonVariant.secondary,
                  loading: busy,
                  onPressed: onAction,
                  semanticsId: semanticsId,
                ),
              ],
            ],
          ),
          if (expansion != null)
            Padding(
              padding: EdgeInsets.only(left: lane, top: BondSpace.s12),
              child: expansion,
            ),
          if (result != null)
            Padding(
              padding: EdgeInsets.only(left: lane, top: BondSpace.s8),
              child: result,
            ),
          if (error != null)
            Padding(
              padding: EdgeInsets.only(left: lane, top: BondSpace.s8),
              child: BondBanner(title: error!, tone: BondToneRole.danger),
            ),
        ],
      ),
    );
  }
}
