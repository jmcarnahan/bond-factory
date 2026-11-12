import 'package:bond_notify/bond_notify.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

import 'bond_notice_row.dart';

/// The inbox: a header (title, unread count, Mark all read), then a column of
/// [BondNoticeRow]. Loading, empty and error lines are inline. The list does
/// not scroll itself; put it in the page's scroll view. When [undoNoticeId]
/// names a row, an undo line shows under it.
class BondNoticeList extends StatelessWidget {
  const BondNoticeList({
    super.key,
    required this.notices,
    required this.now,
    this.loading = false,
    this.error,
    this.onRetry,
    this.unreadCount,
    this.labels = const NoticeLabels(),
    this.onOpen,
    this.onAction,
    this.onDismiss,
    this.onMarkAllRead,
    this.onUndo,
    this.undoNoticeId,
    this.semanticsPrefix,
  });

  final List<Notice> notices;
  final DateTime now;
  final bool loading;
  final Object? error;
  final VoidCallback? onRetry;

  /// The server's unread number, which can exceed the loaded rows. Null counts the loaded rows.
  final int? unreadCount;
  final NoticeLabels labels;
  final void Function(Notice notice)? onOpen;
  final void Function(Notice notice, String action)? onAction;
  final void Function(Notice notice)? onDismiss;
  final VoidCallback? onMarkAllRead;
  final void Function(Notice notice)? onUndo;
  final String? undoNoticeId;

  /// Rows take `<prefix>.row-<id>`; the header and lines take `<prefix>.mark-all`,
  /// `<prefix>.retry` and `<prefix>.undo`.
  final String? semanticsPrefix;

  String? _id(String s) => semanticsPrefix == null ? null : '$semanticsPrefix.$s';

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final text = BondText(t);
    final unread = unreadCount ?? notices.where((n) => n.unread).length;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Expanded(
              child: Wrap(
                spacing: BondSpace.s8,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  Text(labels.inboxTitle, style: text.lead),
                  if (unread > 0) Text(labels.unreadCount(unread), style: text.label),
                ],
              ),
            ),
            if (unread > 0)
              BondButton(
                label: labels.markAllRead,
                variant: BondButtonVariant.quiet,
                onPressed: onMarkAllRead,
                semanticsId: _id('mark-all'),
              ),
          ],
        ),
        BondSpace.h8,
        if (error != null)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: BondSpace.s8),
            child: Wrap(
              spacing: BondSpace.s12,
              runSpacing: BondSpace.s4,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                Icon(Icons.error_outline, size: BondLayout.icon, color: t.danger.press),
                Text(labels.loadError, style: text.small),
                if (onRetry != null)
                  BondButton(
                    label: labels.retry,
                    variant: BondButtonVariant.secondary,
                    onPressed: onRetry,
                    semanticsId: _id('retry'),
                  ),
              ],
            ),
          ),
        if (loading)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: BondSpace.s8),
            child: Semantics(
              liveRegion: true,
              child: Row(
                children: [
                  const SizedBox(
                    width: BondLayout.icon,
                    height: BondLayout.icon,
                    child: CircularProgressIndicator(strokeWidth: BondLayout.rule),
                  ),
                  BondSpace.w12,
                  Expanded(child: Text(labels.loading, style: text.label)),
                ],
              ),
            ),
          ),
        if (!loading && error == null && notices.isEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: BondSpace.s16),
            child: Text(labels.empty, style: text.small),
          ),
        for (final n in notices) ...[
          BondNoticeRow(
            key: ValueKey(n.id),
            notice: n,
            now: now,
            labels: labels,
            onOpen: onOpen,
            onAction: onAction,
            onDismiss: onDismiss,
            semanticsId: _id('row-${n.id}'),
          ),
          if (undoNoticeId == n.id)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: BondSpace.s12),
              child: Wrap(
                crossAxisAlignment: WrapCrossAlignment.center,
                spacing: BondSpace.s8,
                children: [
                  Text(labels.markedDone, style: text.small),
                  BondButton(
                    label: labels.undo,
                    variant: BondButtonVariant.quiet,
                    onPressed: onUndo == null ? null : () => onUndo!(n),
                    semanticsId: _id('undo'),
                  ),
                ],
              ),
            ),
          BondSpace.h8,
        ],
      ],
    );
  }
}
