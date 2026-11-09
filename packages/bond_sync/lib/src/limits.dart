/// Chunking and give-up limits of the uploader.
library;

const int kChunkSize = 100;
const int kChunkBytes = 512 * 1024;
const int kTransientMaxCount = 8;
const Duration kTransientMaxSpan = Duration(minutes: 15);
const Duration kTransientStale = Duration(minutes: 10);

/// Upper bound on one request: at most [chunkSize] ops and [chunkBytes] JSON
/// bytes (the server answers 413 over 1 MiB and the SDK would retry that
/// forever), and at most `sendCaps[table:action]` ops of one kind.
///
/// After [transientMaxCount] counted failures spanning [transientMaxSpan] the
/// transaction's unanswered ops are refused (`server_error`). A count idle for
/// [transientStale] starts over.
class UploadLimits {
  const UploadLimits({
    this.chunkSize = kChunkSize,
    this.chunkBytes = kChunkBytes,
    this.sendCaps = const {},
    this.transientMaxCount = kTransientMaxCount,
    this.transientMaxSpan = kTransientMaxSpan,
    this.transientStale = kTransientStale,
  });

  final int chunkSize;
  final int chunkBytes;
  final Map<String, int> sendCaps;
  final int transientMaxCount;
  final Duration transientMaxSpan;
  final Duration transientStale;
}
