import 'package:bond_notify/bond_notify.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

/// The unread count as a small badge, over the top right corner of [child]
/// or alone when there is none. Hidden at 0; "99+" above 99. Not tappable:
/// wrap it in the control that opens the inbox.
class BondNoticeBadge extends StatelessWidget {
  const BondNoticeBadge({
    super.key,
    required this.unread,
    this.labels = const NoticeLabels(),
    this.semanticsId,
    this.child,
  });

  final int unread;
  final NoticeLabels labels;
  final String? semanticsId;
  final Widget? child;

  @override
  Widget build(BuildContext context) {
    if (unread <= 0) return child ?? const SizedBox.shrink();
    final t = BondTokens.of(context);
    final pill = bondSemantics(
      id: semanticsId,
      label: labels.unreadCount(unread),
      excludeChildren: true,
      child: Container(
        constraints: const BoxConstraints(minWidth: BondSpace.s20, minHeight: BondSpace.s20),
        padding: const EdgeInsets.symmetric(horizontal: BondSpace.s4),
        alignment: Alignment.center,
        decoration: BoxDecoration(color: t.danger.base, borderRadius: t.shape.r12All),
        child: Text(
          unread > 99 ? '99+' : '$unread',
          style: BondText(t).style(BondText.caption12, BondText.semibold, color: t.onFill),
        ),
      ),
    );
    if (child == null) return pill;
    return Stack(
      clipBehavior: Clip.none,
      children: [
        child!,
        Positioned(top: -BondSpace.s4, right: -BondSpace.s4, child: pill),
      ],
    );
  }
}
