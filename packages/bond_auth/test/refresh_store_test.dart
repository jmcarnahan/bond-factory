import 'package:bond_auth/bond_auth.dart';
import 'package:test/test.dart';

void main() {
  test('in-memory store saves, loads and clears', () async {
    final s = InMemoryRefreshTokenStore();
    expect(await s.load(), isNull);
    await s.save('r1');
    await s.reload();
    expect(await s.load(), 'r1');
    await s.clear();
    expect(await s.load(), isNull);
  });

  test('no-op store stores nothing', () async {
    const s = NoRefreshTokenStore();
    await s.save('r1');
    await s.reload();
    expect(await s.load(), isNull);
    await s.clear();
  });

  test('AuthSession.refreshToken defaults to null', () {
    const bare = AuthSession(token: 't', userId: 'u');
    expect(bare.refreshToken, isNull);
    expect(const AuthSession(token: 't', userId: 'u', refreshToken: 'r').refreshToken, 'r');
  });

  test('providers: the new fields read, absent keys give defaults', () {
    final p = AuthProviders.fromJson({
      'signin': [
        {'id': 'google', 'label': 'Google'},
        {'id': 'microsoft'},
        {'label': 'no id'},
      ],
      'break_glass': true,
      'default_flow': 'signin',
    });
    expect(p.signin.map((s) => s.id), ['google', 'microsoft']);
    expect(p.signin.first.label, 'Google');
    expect(p.signin.last.label, 'microsoft');
    expect(p.breakGlass, isTrue);
    expect(p.defaultFlow, 'signin');
    final d = AuthProviders.fromJson({});
    expect(d.signin, isEmpty);
    expect(d.breakGlass, isFalse);
    expect(d.defaultFlow, 'firebase');
    expect(const AuthProviders().signin, isEmpty);
  });
}
