import 'package:bond_notify/bond_notify.dart';
import 'package:flutter/widgets.dart';

/// The inbox: a column of [BondNoticeRow]; empty and loading states inline.
class BondNoticeList extends StatelessWidget {
  const BondNoticeList({
    super.key,
    required this.notices,
    this.labels = const NoticeLabels(),
    this.loading = false,
    this.onOpen,
    this.onAction,
    this.onMarkAllRead,
    this.semanticsPrefix,
  });

  final List<Notice> notices;
  final NoticeLabels labels;
  final bool loading;
  final void Function(Notice notice)? onOpen;
  final void Function(Notice notice, String action)? onAction;
  final VoidCallback? onMarkAllRead;

  /// Rows take `<prefix>.row-<id>`.
  final String? semanticsPrefix;

  @override
  Widget build(BuildContext context) => const SizedBox.shrink();
}
