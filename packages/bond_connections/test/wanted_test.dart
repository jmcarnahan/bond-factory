import 'package:bond_connections/bond_connections.dart';
import 'package:test/test.dart';

void main() {
  test('WantedSet.fromJson reads every field and tolerates gaps', () {
    final w = WantedSet.fromJson({
      'id': 'mail_send',
      'provider': 'google',
      'label': 'Send mail',
      'scopes': ['a', 'b'],
      'granted': true,
    });
    expect(w.id, 'mail_send');
    expect(w.provider, 'google');
    expect(w.label, 'Send mail');
    expect(w.scopes, ['a', 'b']);
    expect(w.granted, isTrue);
    final bare = WantedSet.fromJson({'id': 'x'});
    expect(bare.scopes, isEmpty);
    expect(bare.granted, isFalse);
  });

  test('ConnectionList: wanted parses from the map form, defaults to empty', () {
    final withSets = ConnectionList.fromJson({
      'connections': [
        {'provider': 'google', 'connected': true},
      ],
      'wanted': [
        {'id': 's', 'provider': 'google', 'label': 'L', 'scopes': ['x'], 'granted': false},
      ],
    });
    expect(withSets.connections.single.provider, 'google');
    expect(withSets.wanted.single.id, 's');
    final legacy = ConnectionList.fromJson([
      {'provider': 'microsoft'},
    ]);
    expect(legacy.connections.single.provider, 'microsoft');
    expect(legacy.wanted, isEmpty);
    expect(const ConnectionList().wanted, isEmpty);
  });

  test('ConnectionReturn.attempt is parsed and cleaned', () {
    final url = Uri.parse('https://x.invalid/p?connection=connected&provider=google&attempt=ab_1-C&keep=1');
    final r = ConnectionReturn.parse(url)!;
    expect(r.attempt, 'ab_1-C');
    expect(ConnectionReturn.cleaned(url).toString(), 'https://x.invalid/p?keep=1');
    expect(ConnectionReturn.parse(Uri.parse('https://x.invalid/?connection=error'))!.attempt, isNull);
  });
}
