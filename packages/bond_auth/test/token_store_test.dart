import 'package:bond_auth/bond_auth.dart';
import 'package:test/test.dart';

class _FailingClear extends InMemoryTokenStore {
  _FailingClear(super.token);

  @override
  Future<void> clear() async => throw const TokenStoreException('locked');
}

void main() {
  test('InMemoryTokenStore saves, loads and clears', () async {
    final s = InMemoryTokenStore();
    expect(s.token, isNull);
    await s.save('t1');
    expect(s.token, 't1');
    expect(await s.load(), 't1');
    await s.clear();
    expect(s.token, isNull);
  });

  test('ReloadableTokenStore caches and reloads from the wrapped store', () async {
    final inner = InMemoryTokenStore('old');
    final s = ReloadableTokenStore(inner);
    expect(s.token, isNull, reason: 'nothing loaded yet');
    expect(await s.reload(), 'old');
    expect(s.token, 'old');
    inner.token = 'changed elsewhere';
    expect(s.token, 'old', reason: 'the cache is only refreshed by reload');
    await s.load();
    expect(s.token, 'changed elsewhere');
  });

  test('ReloadableTokenStore writes through', () async {
    final inner = InMemoryTokenStore();
    final s = ReloadableTokenStore(inner);
    await s.save('t');
    expect(inner.token, 't');
    expect(s.token, 't');
    await s.clear();
    expect(inner.token, isNull);
    expect(s.token, isNull);
  });

  test('ReloadableTokenStore keeps its cache when the wrapped clear fails', () async {
    final s = ReloadableTokenStore(_FailingClear('t'));
    await s.reload();
    await expectLater(s.clear(), throwsA(isA<TokenStoreException>()));
    expect(s.token, 't', reason: 'the cache still matches what is stored');
    expect(await s.load(), 't');
  });

  test('LiveTokenForgetter clears and tells the app', () async {
    final store = InMemoryTokenStore('t');
    var told = 0;
    await LiveTokenForgetter(store, onForgotten: () => told++).forget();
    expect(store.token, isNull);
    expect(told, 1);
  });

  test('TokenStoreException prints its message', () {
    expect(const TokenStoreException('locked').toString(), contains('locked'));
  });
}
