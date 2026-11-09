import 'package:flutter/material.dart';

import '../primitives/bond_pressable.dart';
import '../semantics.dart';
import '../tokens/tokens.dart';

class BondBottomNavItem {
  const BondBottomNavItem({
    required this.icon,
    required this.label,
    this.badge,
    this.semanticsLabel,
    this.semanticsId,
  });

  final IconData icon;
  final String label;
  final int? badge;

  /// What a screen reader says, count included ("Messages, 3 unread"), in the
  /// person's language. Without it the label and the real count are read.
  final String? semanticsLabel;

  /// Identifier a driver finds this item by.
  final String? semanticsId;
}

/// The phone app's bottom bar: every item shows its label. It is part of the
/// page, never a sheet. A long label shrinks to fit its slot rather than being
/// cut off, and the count pill stops growing with system text at a cap.
class BondBottomNav extends StatelessWidget {
  const BondBottomNav({super.key, required this.items, required this.currentIndex, required this.onTap});

  final List<BondBottomNavItem> items;
  final int currentIndex;
  final ValueChanged<int> onTap;

  static String _spoken(BondBottomNavItem item) {
    if (item.semanticsLabel != null) return item.semanticsLabel!;
    final badge = item.badge ?? 0;
    return badge > 0 ? '${item.label}, $badge' : item.label;
  }

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    return Container(
      decoration: BoxDecoration(color: t.surface, border: Border(top: BorderSide(color: t.line))),
      child: SafeArea(
        top: false,
        child: Row(
          children: [
            for (var i = 0; i < items.length; i++)
              Expanded(
                child: bondSemantics(
                  id: items[i].semanticsId,
                  label: _spoken(items[i]),
                  button: true,
                  selected: i == currentIndex,
                  onTap: () => onTap(i),
                  excludeChildren: true,
                  child: BondPressable(
                    onTap: () => onTap(i),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(vertical: BondSpace.s8),
                      child: _Item(item: items[i], selected: i == currentIndex),
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _Item extends StatelessWidget {
  const _Item({required this.item, required this.selected});

  final BondBottomNavItem item;
  final bool selected;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final text = BondText(t);
    final badge = item.badge ?? 0;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Stack(
          clipBehavior: Clip.none,
          children: [
            Icon(item.icon, size: BondLayout.iconLg, color: selected ? t.accent.base : t.muted),
            if (badge > 0)
              Positioned(
                right: -BondSpace.s8,
                top: -BondSpace.s4,
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: BondSpace.s4),
                  decoration: BoxDecoration(color: t.danger.base, borderRadius: BondRadius.pillAll),
                  child: MediaQuery.withClampedTextScaling(
                    maxScaleFactor: 1.2,
                    child: Text(badge > 99 ? '99+' : '$badge',
                        style: text.style(BondText.label13, BondText.semibold, color: t.onFill)),
                  ),
                ),
              ),
          ],
        ),
        BondSpace.h4,
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: BondSpace.s4),
          child: FittedBox(
            fit: BoxFit.scaleDown,
            child: Text(
              item.label,
              maxLines: 1,
              softWrap: false,
              style: text.style(BondText.label13, selected ? BondText.semibold : BondText.medium,
                  color: selected ? t.ink : t.muted),
            ),
          ),
        ),
      ],
    );
  }
}
