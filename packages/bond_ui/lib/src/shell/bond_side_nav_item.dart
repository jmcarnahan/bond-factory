import 'package:flutter/material.dart';

import '../primitives/bond_pressable.dart';
import '../semantics.dart';
import '../tokens/tokens.dart';

/// One sidebar destination. [id] is any string the app uses for a place
/// (a route path, a tab key); the nav only compares it with `selectedId`.
/// [count] shows as a badge when above zero.
class BondNavDestination {
  const BondNavDestination({
    required this.id,
    required this.icon,
    required this.label,
    this.count,
    this.semanticsLabel,
    this.semanticsId,
  });

  final String id;
  final IconData icon;
  final String label;
  final int? count;

  /// What a screen reader says, count included ("Inbox, 3 unread"), in the
  /// person's language. Without it the label and the bare count are read.
  final String? semanticsLabel;

  /// Identifier a driver finds this destination by.
  final String? semanticsId;
}

/// A run of destinations under an optional section label. A [collapsible]
/// group shows its label as a button that folds the run inline.
class BondNavGroup {
  const BondNavGroup({
    required this.items,
    this.label,
    this.collapsible = false,
    this.startsExpanded = true,
    this.semanticsId,
  });

  final String? label;
  final List<BondNavDestination> items;
  final bool collapsible;
  final bool startsExpanded;

  /// Identifier of the group header button (collapsible groups only).
  final String? semanticsId;
}

/// A destination row: icon and label with a count pill, or in [rail] mode an
/// icon with a dot.
class BondNavTile extends StatelessWidget {
  const BondNavTile({
    super.key,
    required this.destination,
    required this.active,
    required this.onTap,
    this.rail = false,
  });

  final BondNavDestination destination;
  final bool active;
  final VoidCallback onTap;
  final bool rail;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final text = BondText(t);
    final d = destination;
    final count = d.count ?? 0;
    final iconColor = active ? t.ink : t.muted;
    final Widget content = rail
        ? Stack(
            alignment: Alignment.center,
            children: [
              Icon(d.icon, size: BondLayout.icon, color: iconColor),
              if (count > 0)
                Positioned(
                  top: BondSpace.s8,
                  right: BondSpace.s4,
                  child: Container(
                    width: BondLayout.dot,
                    height: BondLayout.dot,
                    decoration: BoxDecoration(color: t.danger.base, shape: BoxShape.circle),
                  ),
                ),
            ],
          )
        : Row(
            children: [
              Icon(d.icon, size: BondLayout.icon, color: iconColor),
              BondSpace.w12,
              Expanded(
                child: Text(
                  d.label,
                  overflow: TextOverflow.ellipsis,
                  style: text.style(BondText.small14, active ? BondText.semibold : BondText.medium,
                      color: active ? t.ink : t.body),
                ),
              ),
              if (count > 0) _CountPill(count),
            ],
          );
    return bondSemantics(
      id: d.semanticsId,
      label: d.semanticsLabel ?? (count > 0 ? '${d.label}, $count' : d.label),
      button: true,
      selected: active,
      onTap: onTap,
      excludeChildren: true,
      child: BondPressable(
        onTap: onTap,
        borderRadius: t.shape.r12All,
        color: active ? t.ground : null,
        child: Container(
          height: BondLayout.control,
          padding: const EdgeInsets.symmetric(horizontal: BondSpace.s12),
          child: content,
        ),
      ),
    );
  }
}

class _CountPill extends StatelessWidget {
  const _CountPill(this.count);

  final int count;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    return Container(
      constraints: const BoxConstraints(minWidth: BondSpace.s20),
      padding: const EdgeInsets.symmetric(horizontal: BondSpace.s8, vertical: BondSpace.s4),
      decoration: BoxDecoration(color: t.danger.base, borderRadius: BondRadius.pillAll),
      child: Text(
        count > 99 ? '99+' : '$count',
        textAlign: TextAlign.center,
        style: BondText(t).style(BondText.label13, BondText.semibold, color: t.onFill),
      ),
    );
  }
}
