import 'package:flutter/widgets.dart';

/// Every string a bond_ui primitive shows, with English defaults. Apps that
/// need another language supply their own [BondLabels] through
/// [BondLabelsScope]; the package depends on no localisation library.
@immutable
class BondLabels {
  const BondLabels({
    this.confirm = 'Confirm',
    this.cancel = 'Cancel',
    this.clear = 'Clear',
    this.today = 'Today',
    this.select = 'Select',
    this.none = 'None',
    this.required = 'Required',
    this.loading = 'Loading',
    this.retry = 'Retry',
    this.showMore = 'Show more',
    this.showLess = 'Show less',
    this.close = 'Close',
    this.done = 'Done',
    this.edit = 'Edit',
    this.save = 'Save',
    this.search = 'Search',
    this.noResults = 'No results',
    this.searching = 'Searching',
    this.searchFailed = 'Search failed. Try again.',
    this.remove = 'Remove',
    this.areYouSure = 'Are you sure?',
    this.selectDate = 'Select date',
    this.selectTime = 'Select time',
    this.previousMonth = 'Previous month',
    this.nextMonth = 'Next month',
    this.hour = 'Hour',
    this.minute = 'Minute',
    this.am = 'AM',
    this.pm = 'PM',
    this.invalidDate = 'Enter a valid date',
    this.invalidTime = 'Enter a time like 11:45',
    this.photo = 'Photo',
    this.dismiss = 'Dismiss',
    this.sent = 'Sent',
    this.undo = 'Undo',
    this.errorTitle = 'Something went wrong',
    this.staleSince = 'Not updated since',
    this.staleUnknown = 'Not updated yet',
    this.emailLabel = 'Email',
    this.passwordLabel = 'Password',
    this.signIn = 'Sign in',
    this.forgotPassword = 'Forgot password?',
    this.emailRequired = 'Enter your email.',
    this.emailInvalid = 'Enter a valid email address.',
    this.passwordRequired = 'Enter your password.',
    this.resetNeedsEmail = 'Enter your email first, then ask for a reset.',
    this.noPerson = 'Unassigned',
    this.startupFailed = 'The app could not start',
    this.startupFailedHint = 'Check the details below and try again.',
    this.breadcrumbs = 'Breadcrumbs',
    this.monthNames = _months,
    this.monthShort = _monthsShort,
    this.weekdayShort = _weekdays,
  });

  final String confirm;
  final String cancel;
  final String clear;
  final String today;
  final String select;
  final String none;
  final String required;
  final String loading;
  final String retry;
  final String showMore;
  final String showLess;
  final String close;
  final String done;
  final String edit;
  final String save;
  final String search;
  final String noResults;
  final String searching;
  final String searchFailed;
  final String remove;

  /// Prompt shown on the armed second step of an inline confirm.
  final String areYouSure;
  final String selectDate;
  final String selectTime;
  final String previousMonth;
  final String nextMonth;
  final String hour;
  final String minute;
  final String am;
  final String pm;
  final String invalidDate;
  final String invalidTime;
  final String photo;
  final String dismiss;
  final String sent;
  final String undo;
  final String errorTitle;

  /// Prefix before the time in the stale banner: "Not updated since 11:42".
  final String staleSince;
  final String staleUnknown;
  final String emailLabel;
  final String passwordLabel;
  final String signIn;
  final String forgotPassword;
  final String emailRequired;
  final String emailInvalid;
  final String passwordRequired;
  final String resetNeedsEmail;

  /// Chip text when no person is assigned.
  final String noPerson;
  final String startupFailed;
  final String startupFailedHint;

  /// Spoken name of the breadcrumb row.
  final String breadcrumbs;

  /// Twelve full month names, January first.
  final List<String> monthNames;

  /// Twelve short month names, January first.
  final List<String> monthShort;

  /// Seven short weekday names, Monday first.
  final List<String> weekdayShort;

  static const List<String> _months = [
    'January',
    'February',
    'March',
    'April',
    'May',
    'June',
    'July',
    'August',
    'September',
    'October',
    'November',
    'December',
  ];

  static const List<String> _monthsShort = [
    'Jan',
    'Feb',
    'Mar',
    'Apr',
    'May',
    'Jun',
    'Jul',
    'Aug',
    'Sep',
    'Oct',
    'Nov',
    'Dec',
  ];

  static const List<String> _weekdays = [
    'Mon',
    'Tue',
    'Wed',
    'Thu',
    'Fri',
    'Sat',
    'Sun',
  ];

  /// English defaults.
  static const BondLabels defaults = BondLabels();

  /// The labels in scope, or [defaults] when no [BondLabelsScope] exists.
  static BondLabels of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<BondLabelsScope>()?.labels ??
      defaults;
}

/// Supplies [BondLabels] to the widgets below it.
class BondLabelsScope extends InheritedWidget {
  const BondLabelsScope({
    super.key,
    required this.labels,
    required super.child,
  });

  final BondLabels labels;

  @override
  bool updateShouldNotify(BondLabelsScope oldWidget) =>
      labels != oldWidget.labels;
}
