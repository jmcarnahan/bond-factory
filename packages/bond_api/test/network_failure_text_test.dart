import 'package:bond_api/bond_api.dart';
import 'package:test/test.dart';

void main() {
  const labels = ApiLabels();
  const url = 'http://localhost:8013';

  NetworkFailure failure(NetworkFailureKind k, {int? status, String base = url}) =>
      NetworkFailure(k, baseUrl: base, status: status);

  test('each kind names the url', () {
    expect(networkFailureText(failure(NetworkFailureKind.noAnswer), labels),
        'No answer from http://localhost:8013. Is the backend running?');
    expect(networkFailureText(failure(NetworkFailureKind.timeout), labels), 'http://localhost:8013 did not answer in time.');
    expect(networkFailureText(failure(NetworkFailureKind.badBody, status: 200), labels),
        'Unreadable answer from http://localhost:8013.');
    expect(networkFailureText(failure(NetworkFailureKind.http, status: 500), labels), 'http://localhost:8013 answered 500.');
  });

  test('without a url each kind has a plain sentence', () {
    String text(NetworkFailureKind k) => networkFailureText(failure(k, status: 502, base: ''), labels);
    expect(text(NetworkFailureKind.noAnswer), labels.noAnswerNoUrl);
    expect(text(NetworkFailureKind.timeout), labels.timeoutNoUrl);
    expect(text(NetworkFailureKind.badBody), labels.badBodyNoUrl);
    expect(text(NetworkFailureKind.http), 'The server answered with an error (502).');
  });

  test('the baseUrl argument fills in a missing url', () {
    expect(networkFailureText(const ServerError('x', statusCode: 503), labels, baseUrl: url), 'http://localhost:8013 answered 503.');
  });

  test('BadResponse reads as an unreadable answer', () {
    expect(networkFailureText(const BadResponse('/x'), labels, baseUrl: url), 'Unreadable answer from http://localhost:8013.');
  });

  test('a plain NetworkError is a no-answer', () {
    expect(networkFailureText(const NetworkError(), labels, baseUrl: url), contains('No answer from'));
  });

  test('other failures give their detail or the generic line', () {
    expect(networkFailureText(const Conflict('Name taken'), labels), 'Name taken');
    expect(networkFailureText(const Forbidden('no'), labels), labels.generic);
  });

  test('labels can be replaced', () {
    const nl = ApiLabels(noAnswer: 'Geen antwoord van {url}.');
    expect(networkFailureText(failure(NetworkFailureKind.noAnswer), nl), 'Geen antwoord van http://localhost:8013.');
  });

  test('asNetworkFailure leaves 4xx alone', () {
    expect(asNetworkFailure(const Conflict('x'), baseUrl: url), isNull);
    expect(asNetworkFailure(const NotFound(), baseUrl: url)?.kind, NetworkFailureKind.http);
  });
}
