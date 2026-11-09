/// The names an app picks once: database file prefix and logger name.
library;

class BondSyncNames {
  const BondSyncNames({this.prefix = 'bond', this.loggerName = 'bond.sync'});

  /// File-name prefix of the local database (`<prefix>_<userId>.db`).
  final String prefix;

  /// Name for `dart:developer` logs.
  final String loggerName;

  String dbPath(String dir, String userId) => syncDbPath(dir, userId, prefix: prefix);
}

/// The file of [userId]'s database in [dir]: `<dir>/<prefix>_<userId>.db`, the
/// id reduced to characters that are safe in a file name. A pure string
/// function: the separator is `\` only when [dir] uses it and no `/`.
String syncDbPath(String dir, String userId, {String prefix = 'bond'}) {
  final safe = userId.replaceAll(RegExp(r'[^A-Za-z0-9_-]'), '_');
  final sep = dir.contains(r'\') && !dir.contains('/') ? r'\' : '/';
  final base = dir.endsWith('/') || dir.endsWith(r'\') ? dir : '$dir$sep';
  return '$base${prefix}_$safe.db';
}
