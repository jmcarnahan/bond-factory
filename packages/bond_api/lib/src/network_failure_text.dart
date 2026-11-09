/// One sentence for a failed request.
library;

import 'exceptions.dart';
import 'labels.dart';

/// The sentence to show for [e].
///
/// A network failure names where it happened ("No answer from the base URL. Is
/// the backend running?", "the base URL answered 500."). Without a known URL it falls back
/// to the generic lines. Any other failure gives its own [ApiExceptionDetail.userDetail]
/// when it has one and [ApiLabels.generic] otherwise.
///
/// [baseUrl] is used when the failure carries none (a 5xx mapped from a plain
/// response).
String networkFailureText(ApiException e, ApiLabels labels, {String baseUrl = ''}) {
  final f = asNetworkFailure(e, baseUrl: baseUrl);
  if (f == null) return e.userDetail ?? labels.generic;
  final url = f.baseUrl.isEmpty ? baseUrl : f.baseUrl;
  final status = '${f.status ?? 0}';
  final template = url.isEmpty
      ? switch (f.kind) {
          NetworkFailureKind.noAnswer => labels.noAnswerNoUrl,
          NetworkFailureKind.timeout => labels.timeoutNoUrl,
          NetworkFailureKind.badBody => labels.badBodyNoUrl,
          NetworkFailureKind.http => labels.httpErrorNoUrl,
        }
      : switch (f.kind) {
          NetworkFailureKind.noAnswer => labels.noAnswer,
          NetworkFailureKind.timeout => labels.timeout,
          NetworkFailureKind.badBody => labels.badBody,
          NetworkFailureKind.http => labels.httpError,
        };
  return template.replaceAll('{url}', url).replaceAll('{status}', status);
}
