import '../models.dart';
import '../transport.dart';

/// A [SyncTransport] with scripted answers. Each queued entry is served once,
/// in order: a value to return or an error to throw. With nothing queued,
/// uploads answer `ok` for every op and tokens answer [defaultToken].
class FakeSyncTransport implements SyncTransport {
  FakeSyncTransport({this.defaultToken, this.serverNow});

  /// Served by [fetchToken] when no script entry is left.
  SyncToken? defaultToken;

  /// Added to every default upload answer.
  DateTime? serverNow;

  final List<Object> _uploads = [];
  final List<Object> _tokens = [];
  final List<Object> _refreshes = [];

  /// Every request passed to [upload].
  final List<UploadRequest> uploads = [];
  int tokenCalls = 0;
  int refreshCalls = 0;

  /// Queue an [UploadResponse] to return, an error to throw, or a
  /// `UploadResponse Function(UploadRequest)`.
  void enqueueUpload(Object answer) => _uploads.add(answer);

  void enqueueToken(Object answer) => _tokens.add(answer);

  /// Queue a [SessionRefresh] (or an error to throw) for [refreshSession].
  void enqueueRefresh(Object answer) => _refreshes.add(answer);

  /// An `ok` answer for every op of [r].
  static UploadResponse okAll(UploadRequest r, [DateTime? serverNow]) => UploadResponse(
        results: [for (final o in r.ops) SyncOpResult(seq: o.seq, status: 'ok')],
        serverNow: serverNow,
      );

  @override
  Future<SyncToken> fetchToken() async {
    tokenCalls += 1;
    if (_tokens.isNotEmpty) {
      final a = _tokens.removeAt(0);
      if (a is SyncToken) return a;
      throw a;
    }
    final t = defaultToken;
    if (t == null) throw StateError('FakeSyncTransport: no token queued');
    return t;
  }

  @override
  Future<UploadResponse> upload(UploadRequest request) async {
    uploads.add(request);
    if (_uploads.isNotEmpty) {
      final a = _uploads.removeAt(0);
      if (a is UploadResponse) return a;
      if (a is UploadResponse Function(UploadRequest)) return a(request);
      throw a;
    }
    return okAll(request, serverNow);
  }

  @override
  Future<SessionRefresh> refreshSession() async {
    refreshCalls += 1;
    if (_refreshes.isEmpty) return SessionRefresh.renewed;
    final a = _refreshes.removeAt(0);
    if (a is SessionRefresh) return a;
    throw a;
  }
}

/// Wraps a [SyncTransport] and records every call and answer.
class RecordingTransport implements SyncTransport {
  RecordingTransport(this.inner);

  final SyncTransport inner;
  final List<UploadRequest> uploads = [];
  final List<UploadResponse> responses = [];
  final List<Object> errors = [];
  int tokenCalls = 0;
  int refreshCalls = 0;

  @override
  Future<SyncToken> fetchToken() async {
    tokenCalls += 1;
    try {
      return await inner.fetchToken();
    } catch (e) {
      errors.add(e);
      rethrow;
    }
  }

  @override
  Future<UploadResponse> upload(UploadRequest request) async {
    uploads.add(request);
    try {
      final r = await inner.upload(request);
      responses.add(r);
      return r;
    } catch (e) {
      errors.add(e);
      rethrow;
    }
  }

  @override
  Future<SessionRefresh> refreshSession() async {
    refreshCalls += 1;
    return inner.refreshSession();
  }
}
