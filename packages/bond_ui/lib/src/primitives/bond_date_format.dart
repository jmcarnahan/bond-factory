import '../labels.dart';

/// Small date and time formatters over [BondLabels], so the widgets need no
/// `intl`. Internal to bond_ui.
abstract final class BondDateFormat {
  /// `Wed, Nov 8, 2026`.
  static String date(BondLabels l, DateTime d) =>
      '${l.weekdayShort[d.weekday - 1]}, ${l.monthShort[d.month - 1]} ${d.day}, ${d.year}';

  /// `11:45 AM`.
  static String time(BondLabels l, DateTime d) {
    final h = d.hour % 12 == 0 ? 12 : d.hour % 12;
    final m = d.minute.toString().padLeft(2, '0');
    return '$h:$m ${d.hour >= 12 ? l.pm : l.am}';
  }

  /// `November 2026`.
  static String month(BondLabels l, DateTime d) =>
      '${l.monthNames[d.month - 1]} ${d.year}';

  /// `2026-11-08`, for semantics identifiers.
  static String iso(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

  static bool sameDay(DateTime a, DateTime b) =>
      a.year == b.year && a.month == b.month && a.day == b.day;
}
