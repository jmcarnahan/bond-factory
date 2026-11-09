import 'package:flutter/widgets.dart';

import '../theme.dart';
import 'page_scaffold.dart';
import 'ui/ui_components.dart';
import 'ui/ui_primitives.dart';
import 'ui/ui_shell.dart';

/// Every bond_ui widget once, in three sections: primitives, shell, components.
/// Semantics ids are `sdk.ui.<widget>`; the sections live under `pages/ui/`.
class UiPage extends StatelessWidget {
  const UiPage({super.key});

  @override
  Widget build(BuildContext context) {
    return const DemoScope(
      child: PageFrame(
        title: 'UI',
        children: [UiPrimitives(), UiShell(), UiComponents()],
      ),
    );
  }
}
