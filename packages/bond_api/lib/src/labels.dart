/// The sentences [networkFailureText] chooses from.
library;

/// English defaults for every sentence the api package words. `{url}` and
/// `{status}` are replaced by the failure's base URL and HTTP status.
class ApiLabels {
  const ApiLabels({
    this.noAnswer = 'No answer from {url}. Is the backend running?',
    this.timeout = '{url} did not answer in time.',
    this.badBody = 'Unreadable answer from {url}.',
    this.httpError = '{url} answered {status}.',
    this.noAnswerNoUrl = 'Could not reach the server. Check your connection and try again.',
    this.timeoutNoUrl = 'The server did not answer in time.',
    this.badBodyNoUrl = 'The server sent an answer that could not be read.',
    this.httpErrorNoUrl = 'The server answered with an error ({status}).',
    this.generic = 'Something went wrong. Please try again.',
  });

  final String noAnswer;
  final String timeout;
  final String badBody;
  final String httpError;
  final String noAnswerNoUrl;
  final String timeoutNoUrl;
  final String badBodyNoUrl;
  final String httpErrorNoUrl;

  /// For a failure that is neither a network problem nor carries its own detail.
  final String generic;
}
