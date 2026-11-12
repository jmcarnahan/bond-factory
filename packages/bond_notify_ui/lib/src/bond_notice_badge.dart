import 'package:flutter/widgets.dart';

/// The unread count as a small badge; hidden at zero.
class BondNoticeBadge extends StatelessWidget {
  const BondNoticeBadge({super.key, required this.count, this.onTap, this.semanticsId});

  final int count;
  final VoidCallback? onTap;
  final String? semanticsId;

  @override
  Widget build(BuildContext context) => const SizedBox.shrink();
}
