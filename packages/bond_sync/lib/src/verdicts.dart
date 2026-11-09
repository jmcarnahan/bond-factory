/// What the server said about one op, and plain words for it.
library;

/// A verdict for one queued write: `ok`, `rejected` or `skipped`, with the
/// server's `code` and `message` and, on `ok`, a re-keyed id.
class SyncVerdict {
  const SyncVerdict(this.status, this.code, this.message, {this.resolvedId});

  final String status;
  final String? code;
  final String? message;
  final String? resolvedId;

  bool get isOk => status == 'ok';
  bool get isRejected => status == 'rejected';

  /// `ok` needs nothing; a replay the server already has is not news.
  bool get needsAction {
    if (isOk) return false;
    if (status == 'skipped' && code == 'already') return false;
    return true;
  }

  @override
  String toString() => 'SyncVerdict($status${code == null ? '' : ', $code'})';
}

/// Plain words for every verdict `code` a device can be told. Apps extend it
/// with their own codes: `{...kVerdictText, 'my_code': '...'}`.
const Map<String, String> kVerdictText = {
  'invalid': 'The server could not accept this change as written.',
  'invalid_phone': 'That phone number is not valid.',
  'unsupported': 'This change cannot be sent from the device.',
  'not_found': 'The item was not found on the server. It may have been deleted.',
  'forbidden': 'You do not have permission to change that.',
  'conflict': 'That item already exists on the server under another owner.',
  'server_error': 'The server could not take this change.',
  'upload_rejected': 'The server refused this change.',
  'already': 'The server already has this change.',
  'rate_limited': 'The server asked the device to slow down.',
};

/// Plain words for [code]: from [texts] (default [kVerdictText]); the server's
/// own [message] when the code is unknown; a generic line otherwise.
String verdictText(String code, {String? message, Map<String, String> texts = kVerdictText}) {
  final known = texts[code];
  if (known != null) return known;
  final m = message?.trim() ?? '';
  return m.isNotEmpty ? m : 'The server could not take this change.';
}
