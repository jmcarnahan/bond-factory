import 'package:bond_auth/bond_auth.dart';
import 'package:test/test.dart';

void main() {
  test('NotConfiguredIdTokenSource fails every call with notConfigured', () async {
    const s = NotConfiguredIdTokenSource();
    expect(s.isConfigured, isFalse);
    final calls = <Future<Object?> Function()>[
      () => s.currentIdToken(),
      () => s.signInWithEmail('a@example.com', 'x'),
      () => s.sendPasswordReset('a@example.com'),
      () => s.changePassword('a', 'b'),
      () => s.linkedProviders(),
    ];
    for (final call in calls) {
      await expectLater(
        call(),
        throwsA(isA<AuthFailure>().having((e) => e.reason, 'reason', AuthFailureReason.notConfigured)),
      );
    }
  });

  test('NotConfiguredIdTokenSource.signOut is a no-op', () async {
    await const NotConfiguredIdTokenSource().signOut();
  });

  test('FakeIdTokenSource mints mock tokens and records calls', () async {
    final s = FakeIdTokenSource();
    await s.signInWithEmail(' Demo@example.com ', 'pw');
    expect(await s.currentIdToken(forceRefresh: true), 'mock:demo@example.com');
    expect(await s.linkedProviders(), ['password']);
    await s.signOut();
    expect(await s.currentIdToken(), isNull);
    expect(s.calls, ['signInWithEmail', 'currentIdToken(force)', 'linkedProviders', 'signOut', 'currentIdToken']);
  });

  test('FakeIdTokenSource failWith throws on every call', () async {
    final s = FakeIdTokenSource(failWith: const AuthFailure(AuthFailureReason.rateLimited));
    await expectLater(s.currentIdToken(), throwsA(isA<AuthFailure>()));
    expect(s.calls, ['currentIdToken']);
  });
}
