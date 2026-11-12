import 'package:bond_notify/bond_notify.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

import 'notice_when.dart';

/// Action ids in display order. Ids not listed here are ignored.
const List<String> kNoticeActionOrder = ['done', 'snooze', 'cancel'];

/// One notice: unread mark, title, body (two lines), relative time, a last
/// reminder mark, one button per action (Done, Snooze, Cancel) and a dismiss
/// control. Tapping the text calls [onOpen]. [now] is a parameter so the row
/// never reads the clock.
class BondNoticeRow extends StatelessWidget {
  const BondNoticeRow({
    super.key,
    required this.notice,
    required this.now,
    this.labels = const NoticeLabels(),
    this.onOpen,
    this.onAction,
    this.onDismiss,
    this.semanticsId,
  });

  final Notice notice;
  final DateTime now;
  final NoticeLabels labels;
  final void Function(Notice notice)? onOpen;

  /// Called with the wire id: `done`, `snooze` or `cancel`.
  final void Function(Notice notice, String action)? onAction;
  final void Function(Notice notice)? onDismiss;

  /// Row id; actions take `<id>-done` etc, the dismiss control `<id>-dismiss`.
  final String? semanticsId;

  String _actionLabel(String id) => switch (id) {
        'done' => labels.done,
        'snooze' => labels.snooze,
        _ => labels.cancelTask,
      };

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final text = BondText(t);
    final unread = notice.unread;
    final when = noticeWhen(notice.createdAt, now, labels);
    final actions = [
      for (final id in kNoticeActionOrder)
        if (notice.actions.contains(id)) id,
    ];
    String? id(String suffix) => semanticsId == null ? null : bondSemanticsOption(semanticsId!, suffix);
    return Container(
      padding: const EdgeInsets.fromLTRB(BondSpace.s12, BondSpace.s8, BondSpace.s4, BondSpace.s8),
      decoration: BoxDecoration(
        color: unread ? t.accent.wash : t.surface,
        borderRadius: BondRadius.r12All,
        border: Border.all(color: unread ? t.accent.soft : t.line),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: BondSpace.s12, right: BondSpace.s8),
            child: unread
                ? Semantics(
                    label: labels.unread,
                    child: Container(
                      key: const ValueKey('notice-unread-mark'),
                      width: BondSpace.s8,
                      height: BondSpace.s8,
                      decoration: BoxDecoration(color: t.accent.base, shape: BoxShape.circle),
                    ),
                  )
                : const SizedBox(width: BondSpace.s8, height: BondSpace.s8),
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                BondPressable(
                  onTap: onOpen == null ? null : () => onOpen!(notice),
                  semanticLabel: notice.title,
                  semanticsId: semanticsId,
                  child: Padding(
                    padding: const EdgeInsets.symmetric(vertical: BondSpace.s4),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          notice.title,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: unread ? text.bodyStrong : text.body,
                        ),
                        if (notice.body.isNotEmpty)
                          Text(notice.body, maxLines: 2, overflow: TextOverflow.ellipsis, style: text.small),
                        BondSpace.h4,
                        Wrap(
                          spacing: BondSpace.s8,
                          runSpacing: BondSpace.s4,
                          crossAxisAlignment: WrapCrossAlignment.center,
                          children: [
                            if (when.isNotEmpty) Text(when, style: text.caption),
                            if (notice.last)
                              BondStatusChip(BondStatus(labels.lastReminder, tone: BondToneRole.caution)),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
                if (actions.isNotEmpty)
                  Wrap(
                    spacing: BondSpace.s8,
                    runSpacing: BondSpace.s4,
                    children: [
                      for (final a in actions)
                        BondButton(
                          label: _actionLabel(a),
                          variant: a == 'done' ? BondButtonVariant.primary : BondButtonVariant.secondary,
                          onPressed: onAction == null ? null : () => onAction!(notice, a),
                          semanticsId: id(a),
                        ),
                    ],
                  ),
              ],
            ),
          ),
          BondIconButton(
            icon: Icons.close,
            label: labels.dismiss,
            color: t.muted,
            semanticsId: id('dismiss'),
            onPressed: onDismiss == null ? null : () => onDismiss!(notice),
          ),
        ],
      ),
    );
  }
}
