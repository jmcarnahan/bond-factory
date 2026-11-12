import 'package:flutter/material.dart';

import '../primitives/bond_avatar.dart';
import '../primitives/bond_pressable.dart';
import '../semantics.dart';
import '../tokens/tokens.dart';

/// The signed-in person at the foot of the sidebar: [name] and [subtitle]
/// (a role, an e-mail) on a chip. Tapping the chip expands the card in place
/// to show [actions] above it; nothing floats over the page.
///
/// [avatar] is any widget; without one the card draws the person's initials.
class BondAccountCard extends StatelessWidget {
  const BondAccountCard({
    super.key,
    required this.name,
    required this.expanded,
    required this.onToggle,
    this.subtitle,
    this.avatar,
    this.actions = const [],
    this.semanticsId,
  });

  final String name;
  final String? subtitle;
  final Widget? avatar;
  final bool expanded;
  final VoidCallback onToggle;

  /// Usually [BondAccountRow]s plus any inline control (a sign-out confirm).
  final List<Widget> actions;
  final String? semanticsId;

  static String _initials(String name) {
    final parts = name.trim().split(RegExp(r'\s+')).where((p) => p.isNotEmpty).toList();
    if (parts.isEmpty) return '?';
    if (parts.length == 1) return parts.first.substring(0, 1).toUpperCase();
    return (parts.first.substring(0, 1) + parts.last.substring(0, 1)).toUpperCase();
  }

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final text = BondText(t);
    return Container(
      decoration: BoxDecoration(
        color: t.ground,
        borderRadius: t.shape.r16All,
        border: Border.all(color: t.line),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (expanded && actions.isNotEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(BondSpace.s8, BondSpace.s8, BondSpace.s8, 0),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [...actions, Divider(height: 1, color: t.line)],
              ),
            ),
          bondSemantics(
            id: semanticsId,
            label: subtitle == null ? name : '$name, $subtitle',
            button: true,
            expanded: expanded,
            onTap: onToggle,
            excludeChildren: true,
            child: BondPressable(
              onTap: onToggle,
              borderRadius: t.shape.r16All,
              minSize: BondLayout.minTap,
              child: Padding(
                padding: BondSpace.all12,
                child: Row(
                  children: [
                    avatar ?? BondAvatar(initials: _initials(name)),
                    BondSpace.w12,
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(name, maxLines: 1, overflow: TextOverflow.ellipsis, style: text.smallStrong),
                          if (subtitle != null)
                            Text(subtitle!, maxLines: 1, overflow: TextOverflow.ellipsis, style: text.label),
                        ],
                      ),
                    ),
                    Icon(expanded ? Icons.expand_more : Icons.expand_less, size: BondLayout.icon, color: t.muted),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// One tappable row inside an expanded [BondAccountCard].
class BondAccountRow extends StatelessWidget {
  const BondAccountRow({super.key, required this.icon, required this.label, this.onTap, this.semanticsId});

  final IconData icon;
  final String label;
  final VoidCallback? onTap;
  final String? semanticsId;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    return BondPressable(
      onTap: onTap,
      semanticLabel: label,
      semanticsId: semanticsId,
      borderRadius: t.shape.r8All,
      minSize: BondLayout.minTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: BondSpace.s8),
        child: Row(
          children: [
            Icon(icon, size: BondLayout.icon, color: t.muted),
            BondSpace.w12,
            Expanded(child: Text(label, style: BondText(t).style(BondText.small14, BondText.medium))),
          ],
        ),
      ),
    );
  }
}
