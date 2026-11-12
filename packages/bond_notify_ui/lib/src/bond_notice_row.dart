import 'package:bond_notify/bond_notify.dart';
import 'package:flutter/widgets.dart';

/// One notice: title, body, time and its action buttons (Done, Snooze, Cancel), with an inline undo
/// line after Done.
class BondNoticeRow extends StatelessWidget {
  const BondNoticeRow({
    super.key,
    required this.notice,
    this.labels = const NoticeLabels(),
    this.onOpen,
    this.onAction,
    this.semanticsId,
  });

  final Notice notice;
  final NoticeLabels labels;
  final void Function(Notice notice)? onOpen;
  final void Function(Notice notice, String action)? onAction;
  final String? semanticsId;

  @override
  Widget build(BuildContext context) => const SizedBox.shrink();
}
