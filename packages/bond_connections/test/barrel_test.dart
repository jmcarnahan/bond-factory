import 'package:bond_connections/bond_connections.dart';
import 'package:test/test.dart';

void main() {
  test('barrel exports the public names', () {
    expect(ConnectionPhase.values, hasLength(3));
    expect(const ConnectionLabels().connect, 'Connect');
    expect(ConnectionOutcome.values, hasLength(2));
  });
}
