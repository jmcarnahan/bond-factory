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

  /// "3 unread".
  String unreadCount(int n) => n == 1 ? unreadSingular : '$n $unreadPlural';
}
