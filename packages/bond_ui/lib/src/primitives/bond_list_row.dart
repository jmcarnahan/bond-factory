import 'package:flutter/material.dart';

import '../semantics.dart';
import '../tokens/tokens.dart';
import 'bond_dashed_border.dart';
import 'bond_pressable.dart';

/// A list row with a 40 px leading lane (wider on request) and a fixed
/// trailing lane, so columns line up across rows. [accent] draws a coloured
/// bar on the left; [dashed] marks tentative rows.
class BondListRow extends StatelessWidget {
  const BondListRow({
    super.key,
    required this.title,
    this.leading,
    this.subtitle,
    this.trailing,
    this.accent,
    this.dashed = false,
    this.urgent = false,
    this.compact = false,
    this.onTap,
    this.trailingWidth = BondLayout.trailingLane,
    this.leadingWidth = BondLayout.leadingLane,
    this.done = false,
    this.titleMaxLines = 1,
    this.semanticsId,
  });

  final Widget? leading;
  final String title;
  final String? subtitle;
  final Widget? trailing;
  final Color? accent;
  final bool dashed;

  /// A row that needs someone: danger wash and rim.
  final bool urgent;

  /// Drops the leading and trailing lanes: the title gets the whole row.
  final bool compact;
  final VoidCallback? onTap;
  final double trailingWidth;

  /// Width of the leading lane; grows with large text so a time in it is not
  /// cut. The lane is at least [BondLayout.leadingLane] tall.
  final double leadingWidth;

  /// A finished item: the title is struck through and muted.
  final bool done;

  /// Lines the title may use before it ellipsizes.
  final int titleMaxLines;
  final String? semanticsId;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final text = BondText(t);
    final titleStyle = done
        ? text.style(BondText.base16, BondText.semibold, color: t.muted).copyWith(
              decoration: TextDecoration.lineThrough,
              decorationColor: t.muted,
            )
        : text.style(BondText.base16, BondText.semibold);
    final row = Container(
      padding: const EdgeInsets.symmetric(
          horizontal: BondSpace.s12, vertical: BondSpace.s12),
      decoration: BoxDecoration(
        color: urgent ? t.danger.wash : t.surface,
        borderRadius: t.shape.r12All,
        // A dashed row keeps a clear border so it lines up with its solid
        // neighbours; the dashes are painted over it.
        border: Border.all(
          color: dashed
              ? BondTokens.transparent
              : (urgent ? t.danger.soft : t.line),
        ),
      ),
      child: Row(
        children: [
          if (accent != null)
            Container(
              width: BondSpace.s4,
              height: BondLayout.leadingLane,
              margin: const EdgeInsets.only(right: BondSpace.s12),
              decoration: BoxDecoration(
                  color: accent, borderRadius: BondRadius.pillAll),
            ),
          if (!compact) ...[
            ConstrainedBox(
              constraints: BoxConstraints(
                minWidth: leadingWidth,
                maxWidth: leadingWidth,
                minHeight: BondLayout.leadingLane,
              ),
              child: Center(child: leading),
            ),
            BondSpace.w12,
          ],
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(title,
                    maxLines: titleMaxLines,
                    overflow: TextOverflow.ellipsis,
                    style: titleStyle),
                if (subtitle != null)
                  Text(subtitle!,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: done
                          ? text.small.copyWith(color: t.muted)
                          : text.small),
              ],
            ),
          ),
          if (!compact) ...[
            BondSpace.w12,
            SizedBox(
              width: trailingWidth,
              child: Align(alignment: Alignment.centerRight, child: trailing),
            ),
          ],
        ],
      ),
    );
    final shown = dashed ? BondDashedBorder(child: row) : row;
    if (onTap == null) {
      return bondSemantics(
          id: semanticsId, explicitChildNodes: true, child: shown);
    }
    return BondPressable(
      onTap: onTap,
      borderRadius: t.shape.r12All,
      semanticsId: semanticsId,
      child: shown,
    );
  }
}
