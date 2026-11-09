import 'package:bond_connections_ui/bond_connections_ui.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('barrel exports the widgets', () {
    expect(BondConnectionCard, isNotNull);
    expect(BondConnectionsList, isNotNull);
    expect(BondConnectionReturnBanner, isNotNull);
  });
}
