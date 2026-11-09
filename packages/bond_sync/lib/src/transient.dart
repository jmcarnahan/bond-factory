/// Counts server-attributable failures of one transaction, kept in the store.
library;

import 'dart:convert';

import 'limits.dart';
import 'server_clock.dart';
import 'store.dart';

String _metaKey(String txKey) => 'transient:$txKey';

class TransientTracker {
  const TransientTracker(this.store, this.limits, this.clock);

  final SyncStore store;
  final UploadLimits limits;
  final ServerClock clock;

  /// Counts one more failure of [txKey]; true when it is time to give the
  /// transaction up. A count idle for `limits.transientStale` starts over.
  Future<bool> countAndCheck(String txKey) async {
    final now = clock.phoneNow().toUtc();
    var count = 0;
    var firstAt = now;
    final raw = await store.readMeta(_metaKey(txKey));
    if (raw != null) {
      try {
        final m = jsonDecode(raw) as Map;
        var first = DateTime.parse(m['firstAt'] as String);
        var last = DateTime.parse((m['lastAt'] ?? m['firstAt']) as String);
        if (first.isAfter(now)) first = now;
        if (last.isAfter(now)) last = now;
        if (now.difference(last) <= limits.transientStale) {
          count = (m['count'] as num).toInt();
          firstAt = first;
        }
      } catch (_) {
        count = 0;
      }
    }
    count += 1;
    if (count >= limits.transientMaxCount && now.difference(firstAt) >= limits.transientMaxSpan) {
      return true;
    }
    await store.writeMeta(
      _metaKey(txKey),
      jsonEncode({
        'count': count,
        'firstAt': firstAt.toIso8601String(),
        'lastAt': now.toIso8601String(),
      }),
    );
    return false;
  }

  Future<void> forget(String txKey) => store.deleteMeta(_metaKey(txKey));
}
