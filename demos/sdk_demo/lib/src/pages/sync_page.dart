import 'package:flutter/widgets.dart';

import 'page_scaffold.dart';

class SyncPage extends StatelessWidget {
  const SyncPage({super.key});

  @override
  Widget build(BuildContext context) {
    return const PlaceholderPage(id: 'sync', title: 'Sync', module: 'bond_sync', phase: 2);
  }
}
