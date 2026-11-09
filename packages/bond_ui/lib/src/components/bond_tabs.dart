import 'package:flutter/material.dart';

import '../primitives/bond_pressable.dart';
import '../semantics.dart';
import '../tokens/tokens.dart';

class BondTab {
  const BondTab(this.label, {this.count, this.semanticsId});

  final String label;
  final int? count;

  /// Identifier a driver finds this tab by.
  final String? semanticsId;
}

/// Underlined tabs for switching sections of one page, all inline. A row wider
/// than its space scrolls sideways instead of overflowing.
class BondTabs extends StatelessWidget {
  const BondTabs({super.key, required this.tabs, required this.index, required this.onChanged});

  final List<BondTab> tabs;
  final int index;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    return Container(
      decoration: BoxDecoration(border: Border(bottom: BorderSide(color: t.line))),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: Row(
          children: [
            for (var i = 0; i < tabs.length; i++) _TabItem(tab: tabs[i], selected: i == index, onTap: () => onChanged(i)),
          ],
        ),
      ),
    );
  }
}

class _TabItem extends StatelessWidget {
  const _TabItem({required this.tab, required this.selected, required this.onTap});

  final BondTab tab;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final text = BondText(t);
    final count = tab.count;
    return bondSemantics(
      id: tab.semanticsId,
      label: count == null ? tab.label : '${tab.label}, $count',
      button: true,
      selected: selected,
      onTap: onTap,
      excludeChildren: true,
      child: BondPressable(
        onTap: onTap,
        child: Container(
          height: BondLayout.minTap,
          padding: const EdgeInsets.symmetric(horizontal: BondSpace.s16),
          decoration: BoxDecoration(
            border: Border(
              bottom: BorderSide(color: selected ? t.accent.base : BondTokens.transparent, width: BondLayout.rule),
            ),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                tab.label,
                style: text.style(BondText.small14, selected ? BondText.semibold : BondText.medium,
                    color: selected ? t.ink : t.muted),
              ),
              if (count != null) ...[BondSpace.w8, Text('$count', style: text.label)],
            ],
          ),
        ),
      ),
    );
  }
}
