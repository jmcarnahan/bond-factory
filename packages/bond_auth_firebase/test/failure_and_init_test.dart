import 'dart:math';

import 'package:bond_auth/bond_auth.dart';
import 'package:bond_auth_firebase/bond_auth_firebase.dart';
import 'package:bond_auth_firebase/src/firebase_init.dart' show resetFirebaseInit;
import 'package:firebase_core/firebase_core.dart' show FirebaseOptions;
import 'package:flutter_test/flutter_test.dart';

import 'fakes.dart';

FirebaseRuntimeConfig config({bool web = true, bool ios = true}) => FirebaseRuntimeConfig.fromProviders({
      'firebase': {
        'project_id': 'demo-project',
        'auth_domain': 'demo-project.example.org',
        'messaging_sender_id': '123',
        if (web) 'web': {'api_key': 'k-web', 'app_id': 'a-web'},
        if (ios) 'ios': {'api_key': 'k-ios', 'app_id': 'a-ios', 'bundle_id': 'org.example.app'},
      },
    })!;

void main() {
  group('failureFor', () {
    const table = <String, AuthFailureReason>{
      'wrong-password': AuthFailureReason.wrongCredentials,
      'invalid-credential': AuthFailureReason.wrongCredentials,
      'user-not-found': AuthFailureReason.wrongCredentials,
      'invalid-email': AuthFailureReason.invalidEmail,
      'too-many-requests': AuthFailureReason.rateLimited,
      'user-disabled': AuthFailureReason.disabled,
      'network-request-failed': AuthFailureReason.network,
      'internal-error': AuthFailureReason.network,
      'account-exists-with-different-credential': AuthFailureReason.accountExistsWithDifferentCredential,
      'web-context-cancelled': AuthFailureReason.cancelled,
      'popup-closed-by-user': AuthFailureReason.cancelled,
      'credential-already-in-use': AuthFailureReason.alreadyLinked,
      'provider-already-linked': AuthFailureReason.alreadyLinked,
      'weak-password': AuthFailureReason.weakPassword,
      'something-new': AuthFailureReason.other,
    };
    table.forEach((code, reason) {
      test(code, () {
        final f = failureFor(authError(code));
        expect(f.reason, reason);
        expect(f.code, code);
      });
    });
  });

  group('initFirebaseFromRuntimeConfig', () {
    setUp(resetFirebaseInit);

    test('starts once and remembers the success', () async {
      final seen = <FirebaseOptions>[];
      Future<void> init(FirebaseOptions o) async => seen.add(o);
      expect(await initFirebaseFromRuntimeConfig(config(), isWeb: true, initializer: init, appsEmpty: () => true), isTrue);
      expect(await initFirebaseFromRuntimeConfig(config(), isWeb: true, initializer: init, appsEmpty: () => true), isTrue);
      expect(seen, hasLength(1));
      expect(seen.single.projectId, 'demo-project');
      expect(seen.single.authDomain, 'demo-project.example.org');
      expect(seen.single.apiKey, 'k-web');
    });

    test('does not start when an app already exists', () async {
      var started = 0;
      await initFirebaseFromRuntimeConfig(config(),
          isWeb: true, initializer: (_) async => started++, appsEmpty: () => false);
      expect(started, 0);
    });

    test('a failure is not remembered', () async {
      var calls = 0;
      Future<void> flaky(FirebaseOptions o) async {
        if (++calls == 1) throw StateError('boom');
      }

      await expectLater(
        initFirebaseFromRuntimeConfig(config(), isWeb: true, initializer: flaky, appsEmpty: () => true),
        throwsStateError,
      );
      await Future<void>.delayed(Duration.zero);
      expect(await initFirebaseFromRuntimeConfig(config(), isWeb: true, initializer: flaky, appsEmpty: () => true), isTrue);
      expect(calls, 2);
    });

    test('the phone uses the ios block; an incomplete block starts nothing', () async {
      final seen = <FirebaseOptions>[];
      await initFirebaseFromRuntimeConfig(config(), isWeb: false, initializer: (o) async => seen.add(o), appsEmpty: () => true);
      expect(seen.single.iosBundleId, 'org.example.app');
      resetFirebaseInit();
      var started = 0;
      expect(
        await initFirebaseFromRuntimeConfig(config(web: false),
            isWeb: true, initializer: (_) async => started++, appsEmpty: () => true),
        isFalse,
      );
      expect(started, 0);
    });
  });

  group('AppleNonce', () {
    test('raw is 64 hex characters and differs per call', () {
      final a = AppleNonce.generate();
      expect(a.raw, matches(RegExp(r'^[0-9a-f]{64}$')));
      expect(AppleNonce.generate().raw, isNot(a.raw));
    });

    test('hashed is the sha256 of raw', () {
      expect(
        const AppleNonce('abc').hashed,
        'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
      );
    });

    test('a seeded Random makes it repeatable', () {
      expect(AppleNonce.generate(Random(1)).raw, AppleNonce.generate(Random(1)).raw);
    });
  });
}
