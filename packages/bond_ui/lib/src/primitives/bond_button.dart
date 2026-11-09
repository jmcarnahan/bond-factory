import 'package:flutter/material.dart';

import '../semantics.dart';
import '../tokens/tokens.dart';
import 'bond_pressable.dart';

enum BondButtonVariant { primary, secondary, strong, quiet }

enum BondButtonSize { regular, large }

/// The button. Primary uses the accent fill; strong uses the ink fill for the
/// forceful secondary action.
class BondButton extends StatelessWidget {
  const BondButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.variant = BondButtonVariant.primary,
    this.size = BondButtonSize.regular,
    this.icon,
    this.loading = false,
    this.expand = false,
    this.wrapLabel = false,
    this.selected,
    this.semanticsId,
  });

  final String label;
  final VoidCallback? onPressed;
  final BondButtonVariant variant;
  final BondButtonSize size;
  final IconData? icon;
  final bool loading;
  final bool expand;

  /// For labels the server writes: the text wraps and the button grows to
  /// fit, instead of being one fixed-height line that cuts it.
  final bool wrapLabel;

  /// Null for a plain button. For one choice of a set: announced as selected
  /// or not, and drawn in the ink fill when true.
  final bool? selected;
  final String? semanticsId;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final enabled = onPressed != null && !loading;
    final (Color bg, Color fg, Color border) = selected == true
        ? (t.ink, t.onFill, t.ink)
        : switch (variant) {
            BondButtonVariant.primary => (t.accent.base, t.onFill, t.accent.base),
            BondButtonVariant.secondary => (t.surface, t.ink, t.lineStrong),
            BondButtonVariant.strong => (t.ink, t.onFill, t.ink),
            BondButtonVariant.quiet =>
              (BondTokens.transparent, t.ink, BondTokens.transparent),
          };
    // A disabled primary button stays recognisably accented, just faded.
    final disabledBg = switch (variant) {
      BondButtonVariant.quiet => BondTokens.transparent,
      BondButtonVariant.primary => t.accent.soft,
      _ => t.line,
    };
    final disabledFg =
        variant == BondButtonVariant.primary ? t.accent.press : t.muted;
    final large = size == BondButtonSize.large;
    final height = large ? BondLayout.minTap + BondSpace.s8 : BondLayout.control;
    final lit = enabled || loading;
    final textStyle = BondText(t).style(
      large ? BondText.lead18 : BondText.small14,
      BondText.semibold,
      color: lit ? fg : disabledFg,
    );

    final content = Row(
      mainAxisSize: expand ? MainAxisSize.max : MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        if (loading)
          SizedBox(
            width: BondLayout.iconSm,
            height: BondLayout.iconSm,
            child: CircularProgressIndicator(
                strokeWidth: BondLayout.rule, color: fg),
          )
        else if (icon != null)
          Icon(icon, size: BondLayout.icon, color: enabled ? fg : disabledFg),
        if (loading || icon != null) BondSpace.w8,
        Flexible(
          child: Text(
            label,
            textAlign: wrapLabel ? TextAlign.center : null,
            style: textStyle,
            maxLines: wrapLabel ? null : 1,
            overflow: wrapLabel ? TextOverflow.visible : TextOverflow.ellipsis,
          ),
        ),
      ],
    );

    return bondSemantics(
      id: semanticsId,
      label: label,
      button: true,
      enabled: enabled,
      selected: selected,
      // The pressable inside is excluded, so this node carries the tap.
      onTap: enabled ? onPressed : null,
      excludeChildren: true,
      child: BondPressable(
        onTap: enabled ? onPressed : null,
        borderRadius: BondRadius.r12All,
        color: lit ? bg : disabledBg,
        child: Container(
          height: wrapLabel ? null : height,
          constraints: wrapLabel ? BoxConstraints(minHeight: height) : null,
          padding: EdgeInsets.symmetric(
              horizontal: BondSpace.s16, vertical: wrapLabel ? BondSpace.s8 : 0),
          decoration: BoxDecoration(
            borderRadius: BondRadius.r12All,
            border: Border.all(color: lit ? border : BondTokens.transparent),
          ),
          child: Center(widthFactor: expand ? null : 1, child: content),
        ),
      ),
    );
  }
}
