/// Server-sent events: the frame splitter, the frame parser and `ApiClient.sse`.
library;

import 'dart:async';
import 'dart:convert';

import 'client.dart';
import 'exceptions.dart';

/// One dispatched event.
class SseEvent {
  const SseEvent({this.event = 'message', required this.data, this.id, this.retry});

  /// The `event:` name; `message` when the frame had none.
  final String event;

  /// The `data:` lines joined with `\n`.
  final String data;

  /// The `id:` field, when present.
  final String? id;

  /// The `retry:` field (milliseconds), when present and numeric.
  final int? retry;

  /// [data] decoded as JSON when it parses, otherwise the raw string.
  Object? get decoded {
    try {
      return jsonDecode(data);
    } on FormatException {
      return data;
    }
  }

  @override
  String toString() => 'SseEvent($event, $data)';
}

/// Turns arbitrary text chunks into frames. A network read can hold half a
/// frame or three; only a blank line ends a frame. Handles `\n`, `\r\n` and a
/// lone `\r`, including a `\r\n` split across two chunks. Whatever is left at
/// the end is half a frame and is dropped by [finish].
class SseFrameSplitter {
  String _buffer = '';

  /// The whole frames completed by [chunk].
  List<String> add(String chunk) {
    var text = _buffer + chunk;
    // A trailing CR may be the first half of a CRLF: wait for the next chunk.
    var held = '';
    if (text.endsWith('\r')) {
      held = '\r';
      text = text.substring(0, text.length - 1);
    }
    _buffer = text.replaceAll('\r\n', '\n').replaceAll('\r', '\n');
    final frames = _drain();
    _buffer += held;
    return frames;
  }

  /// The frames completed by the end of the stream (a held final CR counts as a
  /// line end). The unfinished rest is dropped.
  List<String> finish() {
    _buffer = _buffer.replaceAll('\r', '\n');
    final frames = _drain();
    _buffer = '';
    return frames;
  }

  List<String> _drain() {
    final frames = <String>[];
    var boundary = _buffer.indexOf('\n\n');
    while (boundary >= 0) {
      frames.add(_buffer.substring(0, boundary));
      _buffer = _buffer.substring(boundary + 2);
      boundary = _buffer.indexOf('\n\n');
    }
    return frames;
  }
}

/// Parses one frame (the text between blank lines, `\n` line ends). Null for a
/// frame that dispatches nothing: only comments or no `data:` line.
SseEvent? parseSseFrame(String frame) {
  var event = 'message';
  String? id;
  int? retry;
  final data = <String>[];
  for (final line in frame.split('\n')) {
    if (line.isEmpty || line.startsWith(':')) continue;
    final colon = line.indexOf(':');
    final field = colon < 0 ? line : line.substring(0, colon);
    var value = colon < 0 ? '' : line.substring(colon + 1);
    if (value.startsWith(' ')) value = value.substring(1);
    switch (field) {
      case 'event':
        event = value;
      case 'data':
        data.add(value);
      case 'id':
        id = value;
      case 'retry':
        retry = int.tryParse(value) ?? retry;
    }
  }
  if (data.isEmpty) return null;
  return SseEvent(event: event, data: data.join('\n'), id: id, retry: retry);
}

extension ApiClientSse on ApiClient {
  /// Opens an event stream. [method] defaults to GET, or POST with a [body].
  ///
  /// [idleTimeout] restarts on every received chunk, so a turn may run for
  /// minutes as long as the server keeps sending (keepalive comments count);
  /// silence for longer ends the stream with a timeout [NetworkFailure]. A 401
  /// is renewed and replayed like any other call. End of stream is terminal:
  /// the stream closes, it never reconnects by itself.
  Stream<SseEvent> sse(
    String path, {
    Object? body,
    String? method,
    Map<String, Object?>? query,
    Duration idleTimeout = const Duration(seconds: 60),
  }) {
    final own = streamClientFactory?.call();
    late final StreamController<SseEvent> out;
    StreamSubscription<String>? reader;
    Timer? idle;
    var cleaned = false;

    Future<void> cleanup() async {
      if (cleaned) return;
      cleaned = true;
      idle?.cancel();
      await reader?.cancel();
      own?.close();
    }

    Future<void> finish() async {
      await cleanup();
      if (!out.isClosed) await out.close();
    }

    Future<void> fail(Object error) async {
      if (!out.isClosed && !cleaned) out.addError(error);
      await finish();
    }

    NetworkFailure failure(NetworkFailureKind kind, String message, [Object? cause]) =>
        NetworkFailure(kind, baseUrl: baseUrl.toString(), message: message, cause: cause?.toString());

    void armIdle() {
      idle?.cancel();
      idle = Timer(idleTimeout, () => unawaited(fail(failure(NetworkFailureKind.timeout, 'Stream timed out'))));
    }

    Future<void> start() async {
      armIdle();
      try {
        final response = await openStream(method ?? (body == null ? 'GET' : 'POST'), path,
            body: body, query: query, client: own);
        if (cleaned) {
          // The listener left while the headers were on the way.
          await response.stream.listen(null).cancel();
          return;
        }
        final splitter = SseFrameSplitter();
        void emit(Iterable<String> frames) {
          for (final f in frames) {
            final event = parseSseFrame(f);
            if (event != null && !out.isClosed) out.add(event);
          }
        }

        reader = response.stream.transform(utf8.decoder).listen(
          (chunk) {
            armIdle();
            emit(splitter.add(chunk));
          },
          onError: (Object e) =>
              unawaited(fail(failure(NetworkFailureKind.noAnswer, 'Connection lost during the stream', e))),
          onDone: () {
            emit(splitter.finish());
            unawaited(finish());
          },
          cancelOnError: true,
        );
      } catch (e) {
        await fail(e is ApiException ? e : failure(NetworkFailureKind.noAnswer, 'Could not open the stream', e));
      }
    }

    out = StreamController<SseEvent>(onListen: () => unawaited(start()), onCancel: cleanup);
    return out.stream;
  }
}
