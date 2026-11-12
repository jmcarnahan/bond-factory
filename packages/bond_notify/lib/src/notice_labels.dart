/// Every string the notice widgets show, with English defaults.
library;

class NoticeLabels {
  const NoticeLabels({
    this.inboxTitle = 'Notifications',
    this.empty = 'No notifications',
    this.markAllRead = 'Mark all read',
    this.done = 'Done',
    this.snooze = 'Snooze',
    this.cancelTask = 'Cancel task',
    this.undo = 'Undo',
    this.lastReminder = 'Last reminder',
    this.unreadSingular = '1 unread',
    this.unreadPlural = 'unread',
    this.loading = 'Loading notifications',
    this.loadError = 'Notifications could not be loaded',
    this.retry = 'Try again',
    this.dismiss = 'Dismiss',
    this.unread = 'Unread',
    this.markedDone = 'Marked done.',
    this.justNow = 'just now',
    this.yesterday = 'yesterday',
    this.minutesAgoSuffix = 'min ago',
    this.hoursAgoSuffix = 'h ago',
    this.monthsShort = const [
      'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', //
      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
    ],
  });

  final String inboxTitle;
  final String empty;
  final String markAllRead;
  final String done;
  final String snooze;
  final String cancelTask;
  final String undo;
  final String lastReminder;
  final String unreadSingular;
  final String unreadPlural;
  final String loading;
  final String loadError;
  final String retry;

  /// Accessible name of the dismiss control on a row.
  final String dismiss;

  /// Accessible name of the unread mark.
  final String unread;
  final String markedDone;
  final String justNow;
  final String yesterday;
  final String minutesAgoSuffix;
  final String hoursAgoSuffix;

  /// Twelve short month names, January first.
  final List<String> monthsShort;

  /// "3 unread".
  String unreadCount(int n) => n == 1 ? unreadSingular : '$n $unreadPlural';

  /// "5 min ago".
  String minutesAgo(int n) => '$n $minutesAgoSuffix';

  /// "3 h ago".
  String hoursAgo(int n) => '$n $hoursAgoSuffix';

  /// "Mar 12", or "Mar 12, 2025" when [year] is given.
  String dateText(int month, int day, {int? year}) {
    final m = monthsShort[(month - 1).clamp(0, monthsShort.length - 1)];
    return year == null ? '$m $day' : '$m $day, $year';
  }
}
