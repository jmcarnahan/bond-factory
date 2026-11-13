// Entrypoint for `make web-compile`: references the open ladder so that `dart compile js` builds it without dart:io.
import 'package:bond_sync_powersync/bond_sync_powersync.dart';

void main() {
  // ignore: unnecessary_statements
  SyncStoreOpener.deleteMovedAside;
  // ignore: unnecessary_statements
  deleteStoreFiles;
}
