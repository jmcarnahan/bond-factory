/// The file side of the recovery ladder where there is no `dart:io` (the web).
///
/// A web database lives in the browser's storage, not in files a path names, so there is nothing to move aside or
/// delete here: every function does nothing, and [renameAside] reports that it moved nothing. (Resetting a web store
/// is the sync SDK's job.)
library;

/// Moves nothing; returns an empty list.
List<String> renameAside(String base, int stamp) => const [];

/// Does nothing.
void removeMovedAside(String base, Set<String> keep) {}

/// Does nothing.
void removeDbFiles(String base) {}
