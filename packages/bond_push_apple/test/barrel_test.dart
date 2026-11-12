import 'package:bond_push/bond_push.dart';
import 'package:bond_push_apple/bond_push_apple.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('every public name exists and constructing the defaults touches no platform channel', () {
    expect(PluginPushTokenSource().token, isA<Function>());
    expect(PluginPushTaps().initialTap, isA<Function>());
    expect(const DefaultPushPlugin(), isA<PushPlugin>());
    expect(PluginPushTokenSource(), isA<PushTokenSource>());
    expect(PluginPushTaps(), isA<PushTaps>());
    expect(PluginPushTaps.parse(null), isNull);
  });
}
