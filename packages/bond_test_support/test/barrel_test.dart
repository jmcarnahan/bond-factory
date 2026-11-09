import 'package:bond_test_support/bond_test_support.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('barrel exports the helpers', () {
    expect(FakeCall<int>(result: 1)(), 1);
    expect(CannedResponses().next('GET', '/x'), isNull);
  });
}
