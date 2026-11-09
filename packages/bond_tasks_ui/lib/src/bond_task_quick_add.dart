import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

/// A one-line title box: enter (or the Add button) calls [onSubmit] with the
/// trimmed title and clears the box. An empty line does nothing.
///
/// With [semanticsId] the box is the id itself and the button `'<id>-add'`.
class BondTaskQuickAdd extends StatefulWidget {
  const BondTaskQuickAdd({
    super.key,
    required this.onSubmit,
    this.labels = const TaskLabels(),
    this.enabled = true,
    this.semanticsId,
  });

  final ValueChanged<String> onSubmit;
  final TaskLabels labels;
  final bool enabled;
  final String? semanticsId;

  @override
  State<BondTaskQuickAdd> createState() => _BondTaskQuickAddState();
}

class _BondTaskQuickAddState extends State<BondTaskQuickAdd> {
  final TextEditingController _c = TextEditingController();

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  void _submit([String? _]) {
    final v = _c.text.trim();
    if (v.isEmpty || !widget.enabled) return;
    _c.clear();
    widget.onSubmit(v);
  }

  @override
  Widget build(BuildContext context) {
    final id = widget.semanticsId;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        Expanded(
          child: BondTextField(
            controller: _c,
            hint: widget.labels.quickAddHint,
            enabled: widget.enabled,
            textInputAction: TextInputAction.done,
            onSubmitted: _submit,
            semanticsId: id,
          ),
        ),
        BondSpace.w8,
        BondButton(
          label: widget.labels.quickAdd,
          onPressed: widget.enabled ? _submit : null,
          semanticsId: id == null ? null : '$id-add',
        ),
      ],
    );
  }
}
