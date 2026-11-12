import 'package:bond_notify/bond_notify.dart';
import 'package:bond_notify_ui/bond_notify_ui.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('barrel exports every public name', () {
    final now = DateTime(2026, 3, 12);
    expect(
      [
        BondNoticeList(notices: const [], now: now),
        BondNoticeRow(notice: const Notice(id: 'a'), now: now),
        const BondNoticeBadge(unread: 1),
      ],
      everyElement(isA<Widget>()),
    );
    expect(noticeWhen(null, now, const NoticeLabels()), '');
    expect(kNoticeActionOrder, ['done', 'snooze', 'cancel']);
  });
}
