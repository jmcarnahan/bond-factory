import 'package:bond_notify/bond_notify.dart';
import 'package:bond_notify_ui/bond_notify_ui.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  final now = DateTime(2026, 3, 12, 12);
  const l = NoticeLabels();
  final cases = <String, (DateTime?, String)>{
    'same instant': (now, 'just now'),
    '59 seconds': (now.subtract(const Duration(seconds: 59)), 'just now'),
    'future': (now.add(const Duration(minutes: 5)), 'just now'),
    '1 minute': (now.subtract(const Duration(minutes: 1)), '1 min ago'),
    '59 minutes': (now.subtract(const Duration(minutes: 59)), '59 min ago'),
    '1 hour': (now.subtract(const Duration(hours: 1)), '1 h ago'),
    '11 hours (same day)': (DateTime(2026, 3, 12, 1), '11 h ago'),
    'across midnight under 24h': (DateTime(2026, 3, 11, 23), 'yesterday'),
    'yesterday morning': (DateTime(2026, 3, 11, 8), 'yesterday'),
    'two days': (DateTime(2026, 3, 10, 12), 'Mar 10'),
    'earlier this year': (DateTime(2026, 1, 2), 'Jan 2'),
    'last year': (DateTime(2025, 12, 31), 'Dec 31, 2025'),
    'null': (null, ''),
  };
  cases.forEach((name, c) {
    test(name, () => expect(noticeWhen(c.$1, now, l), c.$2));
  });

  test('uses the labels given', () {
    const fr = NoticeLabels(justNow: 'a l instant', minutesAgoSuffix: 'mn');
    expect(noticeWhen(now, now, fr), 'a l instant');
    expect(noticeWhen(now.subtract(const Duration(minutes: 5)), now, fr), '5 mn');
  });
}
