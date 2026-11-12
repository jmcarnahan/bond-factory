/// Waiting for the upload queue to empty.
library;

import 'sync_db.dart';

/// Resolves true once the local CRUD queue is empty (every write has been uploaded and acknowledged), or
/// false when [timeout] passes first. Polls the oldest queued transaction every [poll].
///
/// Call it before signing out, between the last local write (for example `SyncPushDevices.unregister`)
/// and `disconnect` / clearing the database: clearing first would lose the queued writes. A false answer
/// means something is still queued (offline, or a write the server keeps refusing): the app decides
/// whether to wait longer or to drop it.
Future<bool> waitForUploadDrain(
  SyncDb db, {
  Duration timeout = const Duration(seconds: 30),
  Duration poll = const Duration(milliseconds: 200),
}) async {
  final end = DateTime.now().add(timeout);
  while (true) {
    if (await db.nextCrudTransaction() == null) return true;
    if (!DateTime.now().isBefore(end)) return false;
    await Future<void>.delayed(poll);
  }
}
