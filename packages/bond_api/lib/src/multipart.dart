/// Multipart upload parts.
library;

import 'package:http/http.dart' as h;
import 'package:http_parser/http_parser.dart' show MediaType;

/// One file in a multipart upload, held in memory (so it works on the web too).
class ApiFile {
  const ApiFile({required this.field, required this.filename, required this.bytes, this.contentType});

  /// The form field name.
  final String field;
  final String filename;
  final List<int> bytes;

  /// E.g. `image/png`. Guessed from [filename] when null (see [guessContentType]).
  final String? contentType;
}

/// The content type for a file name, from its extension: images, PDF, CSV and
/// JSON. Null for anything else (the upload then carries no explicit type).
String? guessContentType(String filename) {
  final dot = filename.lastIndexOf('.');
  final ext = dot < 0 ? '' : filename.substring(dot + 1).toLowerCase();
  return switch (ext) {
    'jpg' || 'jpeg' => 'image/jpeg',
    'png' => 'image/png',
    'heic' => 'image/heic',
    'heif' => 'image/heif',
    'gif' => 'image/gif',
    'webp' => 'image/webp',
    'pdf' => 'application/pdf',
    'csv' => 'text/csv',
    'json' => 'application/json',
    _ => null,
  };
}

/// A fresh request (a request can only be sent once, a replay builds another).
h.MultipartRequest buildMultipart(String method, Uri url, Map<String, String> fields, List<ApiFile> files) {
  final request = h.MultipartRequest(method, url)..fields.addAll(fields);
  for (final f in files) {
    final type = f.contentType ?? guessContentType(f.filename);
    request.files.add(h.MultipartFile.fromBytes(
      f.field,
      f.bytes,
      filename: f.filename,
      contentType: type == null ? null : MediaType.parse(type),
    ));
  }
  return request;
}
