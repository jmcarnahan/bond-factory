import 'package:bond_notify/bond_notify.dart';

/// Relative time for a notice: just now (under a minute), N min ago (under an
/// hour), N h ago (earlier today), yesterday, otherwise a date (with the year
/// when it is not this year). A null [createdAt] gives an empty string; a time
/// in the future counts as just now. Both instants are read in local time.
String noticeWhen(DateTime? createdAt, DateTime now, NoticeLabels labels) {
  if (createdAt == null) return '';
  final c = createdAt.toLocal();
  final n = now.toLocal();
  final diff = n.difference(c);
  if (diff < const Duration(minutes: 1)) return labels.justNow;
  if (diff < const Duration(hours: 1)) return labels.minutesAgo(diff.inMinutes);
  final days = DateTime.utc(n.year, n.month, n.day).difference(DateTime.utc(c.year, c.month, c.day)).inDays;
  if (days == 0) return labels.hoursAgo(diff.inHours);
  if (days == 1) return labels.yesterday;
  return labels.dateText(c.month, c.day, year: c.year == n.year ? null : c.year);
}
