import 'package:flutter/widgets.dart';

import '../theme.dart';
import 'page_scaffold.dart';
import 'ui/ui_components.dart';
import 'ui/ui_primitives.dart';
import 'ui/ui_shell.dart';

/// Every bond_ui widget once, in three sections: primitives, shell, components.
/// Semantics ids are `sdk.ui.<widget>`; the sections live under `pages/ui/`. What the person last did shows
/// under `sdk.ui.last-event`, as a semantics label.
class UiPage extends StatefulWidget {
  const UiPage({super.key});

  @override
  State<UiPage> createState() => _UiPageState();
}

class _UiPageState extends State<UiPage> {
  final ValueNotifier<String> _event = ValueNotifier<String>('nothing yet');

  void _say(String event) => _event.value = event;

  @override
  void dispose() {
    _event.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return DemoScope(
      child: PageFrame(
        title: 'UI',
        children: [
          ValueListenableBuilder<String>(
            valueListenable: _event,
            builder: (context, event, _) => Semantics(
              identifier: 'sdk.ui.last-event',
              label: 'Last event: $event',
              container: true,
              excludeSemantics: true,
              child: Text('Last event: $event', key: const Key('ui-last-event')),
            ),
          ),
          UiPrimitives(say: _say),
          UiShell(say: _say),
          UiComponents(say: _say),
        ],
      ),
    );
  }
}
