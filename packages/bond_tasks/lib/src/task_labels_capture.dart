/// Strings of the capture review and the settings form, English defaults.
library;

class CaptureLabels {
  const CaptureLabels({
    this.captureHint = 'Type or dictate what you need to do',
    this.parse = 'Find tasks',
    this.parsing = 'Reading your text',
    this.reviewTitle = 'Review',
    this.asTask = 'Task',
    this.asEvent = 'Event',
    this.addAll = 'Add all',
    this.add = 'Add',
    this.accept = 'Accept',
    this.degradedNotice = 'Some items could not be read fully. Please check them.',
    this.discard = 'Discard',
    this.lowConfidence = 'Check this one',
    this.dateGuessed = 'Date guessed',
    this.degraded = 'Could not read this fully. Please check each item.',
    this.modelUnavailable = 'Smart capture is unavailable. Your text is kept as one task.',
    this.invalidOutput = 'The result could not be read. Your text is kept as one task.',
    this.captureDenied = 'Too many notes in a short time. Try again in a minute.',
    this.noItems = 'Nothing found in that text.',
    this.linkTo = 'Link to',
    this.chooseMatch = 'Choose a match',
    this.noMatch = 'No match',
    this.allDay = 'All day',
    this.missed = 'Missed',
    this.dictate = 'Dictate',
    this.stopDictation = 'Stop',
    this.itemTitle = 'Title',
    this.removeItem = 'Remove this item',
    this.noDate = 'No date',
    this.searchLink = 'Search',
    this.searchLinkHint = 'Search for a match',
    this.kindSwitch = 'Kind',
    this.titleRequired = 'Enter a title.',
    this.droppedOne = '1 item could not be read.',
    this.droppedMany = '{n} items could not be read.',
  });

  final String captureHint;
  final String parse;
  final String parsing;
  final String reviewTitle;
  final String asTask;
  final String asEvent;
  final String addAll;
  final String add;
  final String accept;
  final String degradedNotice;
  final String discard;
  final String lowConfidence;
  final String dateGuessed;
  final String degraded;
  final String modelUnavailable;
  final String invalidOutput;
  final String captureDenied;
  final String noItems;
  final String linkTo;
  final String chooseMatch;
  final String noMatch;
  final String allDay;

  /// An event in the past (a task past its due time is "Overdue").
  final String missed;
  final String dictate;
  final String stopDictation;
  final String itemTitle;
  final String removeItem;
  final String noDate;
  final String searchLink;
  final String searchLinkHint;
  final String kindSwitch;
  final String titleRequired;
  final String droppedOne;
  final String droppedMany;

  /// The notice for [n] items the server discarded ("1 item could not be read.").
  String droppedNotice(int n) => n == 1 ? droppedOne : droppedMany.replaceAll('{n}', '$n');
}

class SettingsLabels {
  const SettingsLabels({
    this.title = 'Task settings',
    this.timeZone = 'Time zone',
    this.workDayStart = 'Work day starts',
    this.workDayEnd = 'Work day ends',
    this.leadMinutes = 'Remind me before',
    this.minutes = 'minutes',
    this.save = 'Save',
    this.saved = 'Saved',
    this.saveFailed = 'Could not save. Try again.',
    this.invalidTime = 'Use the form HH:MM, for example 08:00.',
    this.sameTimes = 'The start and the end must be different times.',
    this.invalidLead = 'Enter a whole number of minutes from 0 to 10080.',
    this.zoneSearchHint = 'Search for a time zone',
    this.quietHoursTemplate = 'Reminders for dated tasks wait while you are off, from {end} to {start}.',
    this.resetToDefault = 'Reset to default',
    this.usingDefault = 'Default',
    this.resetTimeZone = 'Reset time zone to default',
    this.resetWorkDayStart = 'Reset work day start to default',
    this.resetWorkDayEnd = 'Reset work day end to default',
    this.resetLeadMinutes = 'Reset reminder lead time to default',
  });

  final String title;
  final String timeZone;
  final String workDayStart;
  final String workDayEnd;
  final String leadMinutes;
  final String minutes;
  final String save;
  final String saved;
  final String saveFailed;
  final String zoneSearchHint;
  final String invalidTime;
  final String sameTimes;
  final String invalidLead;
  final String quietHoursTemplate;

  /// The inline control next to a setting the person has changed.
  final String resetToDefault;

  /// The quiet hint next to a setting that follows the app default.
  final String usingDefault;

  /// The screen reader names of the four reset controls (the visible text is [resetToDefault]).
  final String resetTimeZone;
  final String resetWorkDayStart;
  final String resetWorkDayEnd;
  final String resetLeadMinutes;

  /// The screen reader name of the reset control for the wire name [field] (`end_of_day`, say).
  String resetNameFor(String field) => switch (field) {
        'time_zone' => resetTimeZone,
        'start_of_day' => resetWorkDayStart,
        'end_of_day' => resetWorkDayEnd,
        _ => resetLeadMinutes,
      };

  /// The quiet hours sentence for a work day of [start] to [end] ("HH:MM" strings).
  String quietHoursText(String start, String end) =>
      quietHoursTemplate.replaceAll('{start}', start).replaceAll('{end}', end);
}
