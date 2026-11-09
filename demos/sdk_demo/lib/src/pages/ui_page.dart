import 'package:flutter/widgets.dart';

import 'page_scaffold.dart';

class UiPage extends StatelessWidget {
  const UiPage({super.key});

  @override
  Widget build(BuildContext context) {
    return const PlaceholderPage(id: 'ui', title: 'UI', module: 'bond_ui', phase: 1);
  }
}
