/// What a header chip says about sync.
library;

/// When several facts hold, the chip says the first of: attention, sending,
/// not connected, offline with changes queued.
class SyncSummary {
  const SyncSummary({
    this.rejected = 0,
    this.offlineQueued = false,
    this.queued = 0,
    this.sending = false,
    this.failing = false,
    this.notConnected = false,
    this.lastSynced,
  });

  /// The summary of the facts: [rejected] notes, [queued] writes, and whether
  /// the device is [connected] (null while there is no status yet).
  factory SyncSummary.of({
    required int rejected,
    required int queued,
    required bool? connected,
    bool uploading = false,
    bool uploadFailing = false,
    bool downloadError = false,
    DateTime? lastSynced,
  }) =>
      SyncSummary(
        lastSynced: lastSynced,
        notConnected: queued == 0 &&
            ((connected == false && lastSynced != null) || (connected != null && downloadError)),
        rejected: rejected,
        queued: queued,
        offlineQueued: connected == false && queued > 0,
        sending: connected == true && queued > 0 && uploading && !uploadFailing,
        failing: connected == true && queued > 0 && uploadFailing,
      );

  /// Writes the server refused that the person has not cleared.
  final int rejected;

  /// Not connected AND something is waiting to be sent.
  final bool offlineQueued;

  /// Writes waiting to be sent (online or not).
  final int queued;

  /// Connected AND something is waiting and the upload is running.
  final bool sending;

  /// Connected, changes waiting, and the uploads keep failing.
  final bool failing;

  /// Nothing is waiting, but the device is not talking to the server.
  final bool notConnected;

  /// When the device last finished a sync, if ever.
  final DateTime? lastSynced;

  bool get needsAttention => rejected > 0;
  bool get isQuiet => !needsAttention && !offlineQueued && !sending && !failing && !notConnected;

  @override
  bool operator ==(Object other) =>
      other is SyncSummary &&
      other.rejected == rejected &&
      other.offlineQueued == offlineQueued &&
      other.queued == queued &&
      other.sending == sending &&
      other.failing == failing &&
      other.notConnected == notConnected &&
      other.lastSynced == lastSynced;

  @override
  int get hashCode => Object.hash(rejected, offlineQueued, queued, sending, failing, notConnected, lastSynced);
}
