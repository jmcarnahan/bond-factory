/// Every string the local alerts show, with English defaults.
library;

class AlertLabels {
  const AlertLabels({
    this.done = 'Done',
    this.snooze = 'Snooze',
    this.cancel = 'Cancel',
    this.closeTitle = 'Due soon',
    this.dueTitle = 'Due now',
    this.pastTitle = 'Overdue',
    this.lastPastTitle = 'Overdue (last reminder)',
  });

  /// Action button titles.
  final String done;
  final String snooze;
  final String cancel;

  /// Notification titles by stage; the body is the task title.
  final String closeTitle;
  final String dueTitle;
  final String pastTitle;
  final String lastPastTitle;

  String titleFor(String stage, {bool last = false}) => switch (stage) {
        'close' => closeTitle,
        'due' => dueTitle,
        _ => last ? lastPastTitle : pastTitle,
      };
}
