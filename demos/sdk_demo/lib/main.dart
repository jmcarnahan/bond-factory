import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter_web_plugins/url_strategy.dart';

import 'src/app.dart';
import 'src/errors.dart';

export 'src/app.dart' show SdkDemoApp;

void main() {
  usePathUrlStrategy();
  WidgetsFlutterBinding.ensureInitialized();
  // Convenience only: the walk still clicks the semantics placeholder after each full load.
  // Walk harness only: never call this in a shipped app.
  SemanticsBinding.instance.ensureSemantics();
  installErrorCapture();
  runApp(const SdkDemoApp());
}
