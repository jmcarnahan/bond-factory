import 'dart:convert';
import 'dart:math';

import 'package:bond_signin/bond_signin.dart';
import 'package:test/test.dart';

void main() {
  group('SignInAttempt', () {
    test('has the contracted shapes', () {
      final a = SignInAttempt.generate();
      expect(a.id, matches(RegExp(r'^[0-9a-f]{32}$')));
      expect(a.deviceSecret, matches(RegExp(r'^[A-Za-z0-9_-]{43}$'))); // 32 bytes, no padding
      expect(base64Url.decode(base64Url.normalize(a.deviceSecret)), hasLength(32));
      expect(a.deviceChallenge, matches(RegExp(r'^[0-9a-f]{64}$')));
    });

    test('challenge is sha256 hex of the secret string and deterministic', () {
      // sha256("abc") from FIPS 180-2.
      expect(SignInAttempt.challengeFor('abc'),
          'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
      final a = SignInAttempt.generate();
      expect(SignInAttempt.challengeFor(a.deviceSecret), a.deviceChallenge);
      expect(SignInAttempt.challengeFor(a.deviceSecret), a.deviceChallenge);
    });

    test('two attempts differ; a seeded source repeats', () {
      expect(SignInAttempt.generate().id, isNot(SignInAttempt.generate().id));
      final x = SignInAttempt.generate(random: Random(7));
      final y = SignInAttempt.generate(random: Random(7));
      expect(x.deviceSecret, y.deviceSecret);
    });

    test('survives a JSON round trip and rejects junk', () {
      final a = SignInAttempt.generate();
      final b = SignInAttempt.fromJson(jsonDecode(jsonEncode(a.toJson())) as Map);
      expect([b.id, b.deviceSecret, b.deviceChallenge], [a.id, a.deviceSecret, a.deviceChallenge]);
      expect(() => SignInAttempt.fromJson({'id': 1}), throwsFormatException);
      final forged = {...a.toJson(), 'device_challenge': SignInAttempt.challengeFor('other')};
      expect(() => SignInAttempt.fromJson(forged), throwsFormatException);
    });

    test('toString never shows the secret', () {
      final a = SignInAttempt.generate();
      expect(a.toString(), isNot(contains(a.deviceSecret)));
    });
  });

  group('SignInReturn', () {
    test('ok', () {
      final r = SignInReturn.parse(Uri.parse('https://app.test/?signin=ok'));
      expect(r.kind, SignInReturnKind.ok);
      expect(r.isError, isFalse);
    });

    test('error with and without a reason', () {
      final r = SignInReturn.parse(Uri.parse('https://app.test/?signin=error&reason=not_invited'));
      expect([r.kind, r.reason, r.isError], [SignInReturnKind.error, 'not_invited', true]);
      expect(SignInReturn.parse(Uri.parse('https://app.test/?signin=error')).reason, 'unknown');
    });

    test('native code and native error', () {
      final r = SignInReturn.parse(Uri.parse('sdkdemo://return/google?attempt=a1&code=c1'));
      expect([r.kind, r.attempt, r.code, r.reason], [SignInReturnKind.native, 'a1', 'c1', null]);
      final e = SignInReturn.parse(Uri.parse('https://api.test/app/return/google?attempt=a1&error=deactivated'));
      expect([e.kind, e.reason, e.code, e.isError], [SignInReturnKind.native, 'deactivated', null, true]);
    });

    test('none for ordinary visits and half-formed returns', () {
      for (final u in ['https://app.test/', 'https://app.test/?x=1', 'https://app.test/?attempt=a1', 'https://app.test/?signin=maybe']) {
        expect(SignInReturn.parse(Uri.parse(u)).kind, SignInReturnKind.none, reason: u);
      }
    });

    test('a return for a foreign attempt does not match the pending one', () {
      final pending = SignInAttempt.generate();
      final foreign = SignInReturn.parse(Uri.parse('https://api.test/app/return/google?attempt=someone-else&code=c1'));
      expect(foreign.matches(pending), isFalse);
      expect(foreign.matches(null), isFalse);
      final mine = SignInReturn.parse(Uri.parse('https://api.test/app/return/google?attempt=${pending.id}&code=c1'));
      expect(mine.matches(pending), isTrue);
      expect(SignInReturn.parse(Uri.parse('https://app.test/?signin=ok')).matches(pending), isFalse);
    });

    test('cleaned strips only the return parameters', () {
      final u = Uri.parse('https://app.test/home?tab=2&signin=error&reason=x&attempt=a&code=c&error=e#frag');
      expect(SignInReturn.cleaned(u).toString(), 'https://app.test/home?tab=2#frag');
      expect(SignInReturn.cleaned(Uri.parse('https://app.test/?signin=ok')).toString(), 'https://app.test/');
    });

    test('toString never shows the code', () {
      final r = SignInReturn.parse(Uri.parse('x://y/z?attempt=a1&code=secretcode'));
      expect(r.toString(), isNot(contains('secretcode')));
    });
  });

  group('SignInLabels', () {
    test('every code has a non-empty default message', () {
      const labels = SignInLabels();
      expect(SignInLabels.codes, hasLength(25));
      for (final c in ['company_suspended', 'provider_not_allowed', 'invalid_request', 'invalid_origin', 'provider_error', 'invalid_id_token', 'unknown_provider', 'invalid_code']) {
        expect(SignInLabels.codes, contains(c));
      }
      for (final c in SignInLabels.codes) {
        expect(labels.messageFor(c), isNotEmpty, reason: c);
        expect(SignInLabels.defaultMessages.containsKey(c), isTrue, reason: c);
      }
      expect(SignInLabels.defaultMessages.keys.toSet(), SignInLabels.codes.toSet());
    });

    test('unlisted and null codes read as unknown; continueWith fills the name', () {
      const labels = SignInLabels();
      expect(labels.messageFor('nope'), labels.messageFor('unknown'));
      expect(labels.messageFor(null), labels.messageFor('unknown'));
      expect(labels.continueWith('Google'), 'Continue with Google');
      expect(labels.title, isNotEmpty);
      expect(labels.inviteOnly, isNotEmpty);
      expect(labels.breakGlass, isNotEmpty);
    });
  });
}
