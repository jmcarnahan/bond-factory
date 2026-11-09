/// Every string the task widgets show, with English defaults.
library;

import 'task_enums.dart';

class TaskLabels {
  const TaskLabels({
    this.title = 'Title',
    this.titleRequired = 'Enter a title.',
    this.titleTooLong = 'Use 255 characters or fewer.',
    this.unrecognisedDate = 'Unrecognised date',
    this.unrecognisedTime = 'Unrecognised time',
    this.notes = 'Notes',
    this.dueDate = 'Due date',
    this.dueTime = 'Due time',
    this.dueTimeNeedsDate = 'Pick a date to set a time.',
    this.noDueDate = 'No date',
    this.assignee = 'Assigned to',
    this.unassigned = 'Unassigned',
    this.checklist = 'Checklist',
    this.addChecklistItem = 'Add item',
    this.checklistItemHint = 'New checklist item',
    this.removeItem = 'Remove item',
    this.reminder = 'Reminder',
    this.remindNone = 'No reminder',
    this.remindMorningOf = 'Morning of',
    this.remind1 = '1 minute before',
    this.remind15 = '15 minutes before',
    this.remind60 = '1 hour before',
    this.remind1440 = '1 day before',
    this.mirror = 'Add to my calendar',
    this.save = 'Save task',
    this.cancel = 'Cancel',
    this.quickAddHint = 'Add a task and press enter',
    this.quickAdd = 'Add',
    this.complete = 'Complete',
    this.reopen = 'Reopen',
    this.delete = 'Delete',
    this.sectionOverdue = 'Overdue',
    this.sectionToday = 'Today',
    this.sectionUpcoming = 'Upcoming',
    this.sectionNoDate = 'No date',
    this.sectionDone = 'Done',
    this.addTime = 'Add a time',
    this.removeTime = 'Remove time',
    this.empty = 'No tasks',
    this.emptyMessage = 'Add a task to get started.',
    this.loading = 'Loading tasks',
    this.loadFailed = 'Tasks could not be loaded.',
    this.retry = 'Retry',
    this.statusOpen = 'Open',
    this.statusDone = 'Done',
    this.statusCancelled = 'Cancelled',
    this.overdue = 'Overdue',
    this.summaryOpen = 'Open',
    this.summaryOverdue = 'Overdue',
    this.summaryToday = 'Due today',
    this.summaryNoDate = 'No date',
    this.external = 'Calendar',
  });

  final String title;
  final String titleRequired;
  final String titleTooLong;
  final String unrecognisedDate;
  final String unrecognisedTime;
  final String notes;
  final String dueDate;
  final String dueTime;
  final String dueTimeNeedsDate;
  final String noDueDate;
  final String assignee;
  final String unassigned;
  final String checklist;
  final String addChecklistItem;
  final String checklistItemHint;
  final String removeItem;
  final String reminder;
  final String remindNone;
  final String remindMorningOf;
  final String remind1;
  final String remind15;
  final String remind60;
  final String remind1440;
  final String mirror;
  final String save;
  final String cancel;
  final String quickAddHint;
  final String quickAdd;
  final String complete;
  final String reopen;
  final String delete;
  final String sectionOverdue;
  final String sectionToday;
  final String sectionUpcoming;
  final String sectionNoDate;
  final String sectionDone;
  final String addTime;
  final String removeTime;
  final String empty;
  final String emptyMessage;
  final String loading;
  final String loadFailed;
  final String retry;
  final String statusOpen;
  final String statusDone;
  final String statusCancelled;
  final String overdue;
  final String summaryOpen;
  final String summaryOverdue;
  final String summaryToday;
  final String summaryNoDate;
  final String external;

  String statusText(TaskStatus s) => switch (s) {
        TaskStatus.open => statusOpen,
        TaskStatus.done => statusDone,
        TaskStatus.cancelled => statusCancelled,
      };

  /// The text for a `remind_minutes_before` value; a custom number reads
  /// "N minutes before".
  String remindText(int minutes) => switch (minutes) {
        kRemindNone => remindNone,
        kRemindMorningOf => remindMorningOf,
        1 => remind1,
        15 => remind15,
        60 => remind60,
        1440 => remind1440,
        _ => '$minutes minutes before',
      };

  /// "2 of 5".
  String checklistProgress(int done, int total) => '$done of $total';
}
