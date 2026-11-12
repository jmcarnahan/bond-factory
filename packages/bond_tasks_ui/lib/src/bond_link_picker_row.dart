import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

/// Links of a task: the chosen ones as removable chips and a search that adds
/// more (results inline). A link already chosen (same kind and id) is not
/// added twice. [onSearch] gets the [kind] and the text.
class BondLinkPickerRow extends StatelessWidget {
  const BondLinkPickerRow({
    super.key,
    required this.links,
    required this.onSearch,
    required this.onChanged,
    this.kind = 'contact',
    this.labels = const TaskLabels(),
    this.semanticsId,
  });

  final List<TaskLink> links;
  final Future<List<TaskLink>> Function(String kind, String query) onSearch;
  final ValueChanged<List<TaskLink>> onChanged;
  final String kind;
  final TaskLabels labels;
  final String? semanticsId;

  static String _name(TaskLink l) => (l.label ?? '').isEmpty ? l.id : l.label!;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(labels.links, style: BondText(t).smallStrong),
        BondSpace.h4,
        BondSearchPicker<TaskLink>(
          onSearch: (q) => onSearch(kind, q),
          labelOf: _name,
          picked: links,
          hint: labels.linkHint,
          onPick: (l) {
            if (links.any((k) => k.kind == l.kind && k.id == l.id)) return;
            onChanged([...links, l]);
          },
          onRemove: (l) => onChanged([
            for (final k in links)
              if (k != l) k,
          ]),
          semanticsId: semanticsId,
        ),
      ],
    );
  }
}
