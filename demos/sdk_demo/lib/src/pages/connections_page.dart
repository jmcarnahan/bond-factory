import 'package:flutter/widgets.dart';

import 'page_scaffold.dart';

class ConnectionsPage extends StatelessWidget {
  const ConnectionsPage({super.key});

  @override
  Widget build(BuildContext context) {
    return const PlaceholderPage(
      id: 'connections',
      title: 'Connections',
      module: 'bond_connections',
      phase: 3,
    );
  }
}
