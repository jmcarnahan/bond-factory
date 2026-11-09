import 'package:bond_auth/bond_auth.dart';
import 'package:test/test.dart';

import 'support.dart';

void main() {
  group('AuthSession.fromToken', () {
    test('reads sub, claims and capabilities', () {
      final s = AuthSession.fromToken(jwt({'sub': 'u1', 'capabilities': ['a', 'b'], 'name': 'N'}));
      expect(s.userId, 'u1');
      expect(s.capabilities, ['a', 'b']);
      expect(s.claims['name'], 'N');
    });

    test('capabilities default to empty', () {
      expect(AuthSession.fromToken(jwt({'sub': 'u1'})).capabilities, isEmpty);
    });

    test('rejects garbage and a missing sub', () {
      expect(() => AuthSession.fromToken('nope'), throwsFormatException);
      expect(() => AuthSession.fromToken('a.b.c'), throwsFormatException);
      expect(() => AuthSession.fromToken(jwt({'name': 'x'})), throwsFormatException);
    });

    test('isExpiredAt follows exp', () {
      final s = AuthSession.fromToken(jwt({'sub': 'u', 'exp': 1000}));
      expect(s.isExpiredAt(DateTime.fromMillisecondsSinceEpoch(999000)), isFalse);
      expect(s.isExpiredAt(DateTime.fromMillisecondsSinceEpoch(1000000)), isTrue);
      expect(s.isExpired, isTrue);
      expect(AuthSession.fromToken(jwt({'sub': 'u'})).isExpired, isFalse);
    });
  });

  group('ClaimListPolicy', () {
    final session = AuthSession.fromToken(jwt({'sub': 'u', 'capabilities': ['tasks.read', 'root']}));

    test('membership', () {
      const p = ClaimListPolicy();
      expect(p.has(session, 'tasks.read'), isTrue);
      expect(p.has(session, 'tasks.write'), isFalse);
    });

    test('a superuser capability passes every check', () {
      const p = ClaimListPolicy(superuser: {'root'});
      expect(p.has(session, 'tasks.write'), isTrue);
    });
  });
}
