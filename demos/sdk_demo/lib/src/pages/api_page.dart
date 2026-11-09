import 'package:flutter/widgets.dart';

import 'page_scaffold.dart';

class ApiPage extends StatelessWidget {
  const ApiPage({super.key});

  @override
  Widget build(BuildContext context) {
    return const PlaceholderPage(id: 'api', title: 'API', module: 'bond_api', phase: 1);
  }
}
