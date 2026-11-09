import 'package:bond_json/bond_json.dart';
import 'package:test/test.dart';

void main() {
  test('barrel exports the readers', () {
    expect(jstr({'a': 'b'}, 'a'), 'b');
    expect(const JsonShapeError('p', 'e', 'a'), isA<Exception>());
  });
}
