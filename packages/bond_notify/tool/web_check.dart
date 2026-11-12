// Entry point for `make test-web`: compiling it proves the browser alert is valid for dart2js.
import 'package:bond_notify/bond_notify.dart';

void main() {
  final alert = browserNoticeAlert();
  alert.requestPermission();
  alert.show(const Notice(id: 'check', title: 'Check', body: 'Compiles for the web'));
}
