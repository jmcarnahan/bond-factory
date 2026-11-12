import 'package:flutter/material.dart';

/// Page frame shared by the demo pages: a title (key `page-title`) and a body.
class PageFrame extends StatelessWidget {
  const PageFrame({super.key, required this.title, required this.children});

  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(title, key: const Key('page-title'), style: Theme.of(context).textTheme.headlineSmall),
        const SizedBox(height: 16),
        ...children,
      ],
    );
  }
}

/// "`<module>` arrives in phase N", found by `sdk.<id>.placeholder`.
class PlaceholderPage extends StatelessWidget {
  const PlaceholderPage({
    super.key,
    required this.id,
    required this.title,
    required this.module,
    required this.phase,
  });

  final String id;
  final String title;
  final String module;
  final int phase;

  @override
  Widget build(BuildContext context) {
    return PageFrame(
      title: title,
      children: [
        Semantics(
          identifier: 'sdk.$id.placeholder',
          child: Text('$module arrives in phase $phase'),
        ),
      ],
    );
  }
}

/// A text whose words are also the semantics label: a browser driver reads
/// labels, not identifiers. The inner text is excluded so it is read once.
Widget labelledText(String id, String text, [TextStyle? style]) => Semantics(
      identifier: id,
      label: text,
      container: true,
      child: ExcludeSemantics(child: Text(text, style: style)),
    );
