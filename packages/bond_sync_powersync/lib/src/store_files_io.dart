/// The file side of the recovery ladder on platforms with `dart:io` (the phone, desktop, the VM).
library;

import 'dart:io';

const _suffixes = ['', '-wal', '-shm', '-journal'];

/// Renames the database at [base] and its siblings to `<name>.bad-<stamp>`; returns the new paths. Never throws.
List<String> renameAside(String base, int stamp) {
  final moved = <String>[];
  for (final suffix in _suffixes) {
    try {
      final f = File('$base$suffix');
      if (f.existsSync()) {
        final to = '$base$suffix.bad-$stamp';
        f.renameSync(to);
        moved.add(to);
      }
    } catch (_) {}
  }
  return moved;
}

/// Deletes every `<db>.bad-*` file of the database at [base] that is not in [keep]. Never throws.
void removeMovedAside(String base, Set<String> keep) {
  try {
    final slash = base.lastIndexOf(RegExp(r'[/\\]'));
    final dir = Directory(base.substring(0, slash));
    final name = base.substring(slash + 1);
    for (final f in dir.listSync()) {
      final n = f.uri.pathSegments.last;
      if (n.startsWith(name) && n.contains('.bad-') && !keep.contains(f.path)) {
        try {
          f.deleteSync();
        } catch (_) {}
      }
    }
  } catch (_) {}
}

/// Deletes the database at [base] and its siblings. Never throws.
void removeDbFiles(String base) {
  for (final suffix in _suffixes) {
    try {
      final f = File('$base$suffix');
      if (f.existsSync()) f.deleteSync();
    } catch (_) {}
  }
}
