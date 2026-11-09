/// Backend-agnostic sync core: wire models, transport, failure mapping,
/// uploader, rejections and the SyncStore seam. Pure Dart, no database import.
library;

export 'src/chunker.dart';
export 'src/failure.dart';
export 'src/ids.dart';
export 'src/limits.dart';
export 'src/models.dart';
export 'src/names.dart';
export 'src/outcome.dart';
export 'src/rejections.dart';
export 'src/server_clock.dart';
export 'src/store.dart';
export 'src/sync_summary.dart';
export 'src/transient.dart';
export 'src/transport.dart';
export 'src/uploader.dart';
export 'src/verdicts.dart';
