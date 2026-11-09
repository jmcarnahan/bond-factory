import 'package:bond_api/bond_api.dart';
import 'package:test/test.dart';

void main() {
  test('barrel exports the public API', () {
    expect(authPathsExcludedFromRenewal, ['/auth/firebase', '/auth/refresh', '/auth/demo']);
    expect(SessionRefresh.values, hasLength(3));
    expect(const ApiLabels().generic, isNotEmpty);
    expect(parseSseFrame('data: x')?.data, 'x');
  });
}
