import 'package:flutter/widgets.dart';

/// A place the app fills with its own dictation control (speech needs a
/// platform plugin, which this package does not depend on). Draws what
/// [builder] returns, or nothing when there is no builder.
class BondDictationSlot extends StatelessWidget {
  const BondDictationSlot({super.key, this.builder});

  final WidgetBuilder? builder;

  @override
  Widget build(BuildContext context) => builder?.call(context) ?? const SizedBox.shrink();
}
