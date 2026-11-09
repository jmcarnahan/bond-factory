import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

import 'bond_checklist.dart';

/// Edits a list of checklist lines in place: tick, remove, and add through a
/// one-line box (enter or the button). New lines get an id from [newId].
///
/// With [semanticsBase]: lines `'<base>-item-<n>'`, removes
/// `'<base>-item-remove-<n>'`, the box `'<base>-add'` and the button
/// `'<base>-add-button'`.
class BondTaskChecklistEditor extends StatefulWidget {
  const BondTaskChecklistEditor({
    super.key,
    required this.items,
    required this.onChanged,
    this.labels = const TaskLabels(),
    this.semanticsBase,
    this.newId,
    this.now,
  });

  final List<ChecklistItem> items;
  final ValueChanged<List<ChecklistItem>> onChanged;
  final TaskLabels labels;
  final String? semanticsBase;

  /// Builds an id for a new line; defaults to a microsecond stamp.
  final String Function()? newId;

  /// The clock used to stamp a ticked line.
  final DateTime Function()? now;

  @override
  State<BondTaskChecklistEditor> createState() => _BondTaskChecklistEditorState();
}

class _BondTaskChecklistEditorState extends State<BondTaskChecklistEditor> {
  final TextEditingController _c = TextEditingController();

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  String? _id(String part) => widget.semanticsBase == null ? null : '${widget.semanticsBase}-$part';

  void _add([String? _]) {
    final text = _c.text.trim();
    if (text.isEmpty) return;
    final id = widget.newId?.call() ?? 'c${DateTime.now().microsecondsSinceEpoch}';
    _c.clear();
    widget.onChanged([...widget.items, ChecklistItem(id: id, text: text)]);
  }

  void _toggle(ChecklistItem item, bool done) {
    final stamp = (widget.now ?? DateTime.now)().toUtc();
    widget.onChanged([
      for (final i in widget.items)
        if (i.id == item.id) (done ? i.copyWith(doneAt: stamp) : i.copyWith(clearDone: true)) else i,
    ]);
  }

  @override
  Widget build(BuildContext context) {
    final l = widget.labels;
    final t = BondTokens.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(l.checklist, style: BondText(t).label),
        BondSpace.h4,
        BondChecklist(
          items: widget.items,
          labels: l,
          semanticsPrefix: _id('item'),
          onToggle: _toggle,
          onRemove: (item) => widget.onChanged([for (final i in widget.items) if (i.id != item.id) i]),
        ),
        Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
              child: BondTextField(
                controller: _c,
                hint: l.checklistItemHint,
                onSubmitted: _add,
                semanticsId: _id('add'),
              ),
            ),
            BondSpace.w8,
            BondButton(
              label: l.addChecklistItem,
              variant: BondButtonVariant.secondary,
              onPressed: _add,
              semanticsId: _id('add-button'),
            ),
          ],
        ),
      ],
    );
  }
}
