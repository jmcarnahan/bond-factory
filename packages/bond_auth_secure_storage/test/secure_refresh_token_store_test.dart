import 'package:bond_auth_secure_storage/bond_auth_secure_storage.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';

/// A map-backed stand-in for the plugin; only read, write and delete are used.
class FakeSecureStorage implements FlutterSecureStorage {
  final Map<String, String> data = {};
  bool failReads = false;
  bool failWrites = false;
  int reads = 0;

  @override
  Future<String?> read({required String key, dynamic iOptions, dynamic aOptions, dynamic lOptions, dynamic webOptions, dynamic mOptions, dynamic wOptions}) async {
    reads++;
    if (failReads) throw StateError('keychain unavailable');
    return data[key];
  }

  @override
  Future<void> write({required String key, required String? value, dynamic iOptions, dynamic aOptions, dynamic lOptions, dynamic webOptions, dynamic mOptions, dynamic wOptions}) async {
    if (failWrites) throw StateError('keychain write refused');
    if (value == null) {
      data.remove(key);
    } else {
      data[key] = value;
    }
  }

  @override
  Future<void> delete({required String key, dynamic iOptions, dynamic aOptions, dynamic lOptions, dynamic webOptions, dynamic mOptions, dynamic wOptions}) async => data.remove(key);

  @override
  dynamic noSuchMethod(Invocation invocation) => throw UnimplementedError('${invocation.memberName}');
}

void main() {
  test('save, load and clear round trip under a namespaced key', () async {
    final fake = FakeSecureStorage();
    final store = SecureRefreshTokenStore(appKey: 'appA', storage: fake);
    expect(await store.load(), isNull);
    await store.save('rt-1');
    expect(fake.data, {'appA.bond_refresh_token': 'rt-1'});
    expect(await store.load(), 'rt-1');
    await store.clear();
    expect(fake.data, isEmpty);
    expect(await store.load(), isNull);
  });

  test('two apps do not share a key', () async {
    final fake = FakeSecureStorage();
    await SecureRefreshTokenStore(appKey: 'appA', storage: fake).save('a');
    expect(await SecureRefreshTokenStore(appKey: 'appB', storage: fake).load(), isNull);
  });

  test('reload is a read and picks up another isolate\'s write', () async {
    final fake = FakeSecureStorage();
    final mine = SecureRefreshTokenStore(appKey: 'appA', storage: fake);
    await mine.save('rt-1');
    await SecureRefreshTokenStore(appKey: 'appA', storage: fake).save('rt-2'); // other isolate rotated
    expect(await mine.load(), 'rt-1'); // cached
    final before = fake.reads;
    await mine.reload();
    expect(fake.reads, before + 1);
    expect(await mine.load(), 'rt-2');
  });

  test('a failing read keeps the cached value instead of throwing', () async {
    final fake = FakeSecureStorage();
    final store = SecureRefreshTokenStore(appKey: 'appA', storage: fake);
    await store.save('rt-1');
    fake.failReads = true;
    await store.reload();
    expect(await store.load(), 'rt-1');
  });

  test('a cold start with a failing read loads null', () async {
    final fake = FakeSecureStorage()..failReads = true;
    expect(await SecureRefreshTokenStore(appKey: 'appA', storage: fake).load(), isNull);
  });

  test('rotation id round trips under its own key and clear removes it', () async {
    final fake = FakeSecureStorage();
    final store = SecureRefreshTokenStore(appKey: 'appA', storage: fake);
    expect(await store.loadRotation(), isNull);
    await store.saveRotation('rot-1');
    expect(fake.data['appA.rotation'], 'rot-1');
    // A cold start in a new store reads it back.
    expect(await SecureRefreshTokenStore(appKey: 'appA', storage: fake).loadRotation(), 'rot-1');
    await store.saveRotation(null);
    expect(fake.data.containsKey('appA.rotation'), isFalse);
    await store.saveRotation('rot-2');
    await store.save('rt');
    await store.clear();
    expect(fake.data, isEmpty);
    expect(await store.loadRotation(), isNull);
  });

  test('a failed write keeps the cache and reports instead of throwing', () async {
    final fake = FakeSecureStorage()..failWrites = true;
    final errors = <Object>[];
    final store = SecureRefreshTokenStore(appKey: 'appA', storage: fake, onError: errors.add);
    await store.save('rt-1');
    await store.saveRotation('rot-1');
    expect(await store.load(), 'rt-1');
    expect(await store.loadRotation(), 'rot-1');
    expect(errors, hasLength(2));
    expect(errors.map((e) => e.toString()).join(), isNot(contains('rt-1')));
    await store.clear(); // reports, never throws
    expect(await store.load(), isNull);
    // With no reporter a failed write is silent.
    await SecureRefreshTokenStore(appKey: 'appA', storage: fake).save('x');
  });
}
