import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../semantics.dart';
import '../tokens/tokens.dart';

/// A small text field that edits a value in place and commits it when the
/// person presses Enter or leaves the field. Nothing opens over the page.
///
/// [onCommit] runs once per change with the trimmed text, and only when the
/// text differs from [value]. When [value] changes from outside (a server
/// answer, a rollback) and the field is not focused, the text follows it.
class BondInlineField extends StatefulWidget {
  const BondInlineField({
    super.key,
    required this.value,
    required this.onCommit,
    this.width,
    this.semanticLabel,
    this.semanticsId,
    this.keyboardType = TextInputType.number,
    this.textAlign = TextAlign.end,
    this.suffix,
    this.enabled = true,
    this.maxLines = 1,
    this.hint,
  });

  final String value;
  final ValueChanged<String> onCommit;
  final double? width;
  final String? semanticLabel;
  final String? semanticsId;
  final TextInputType keyboardType;
  final TextAlign textAlign;

  /// Text after the value inside the box, such as `%`.
  final String? suffix;
  final bool enabled;
  final int maxLines;
  final String? hint;

  @override
  State<BondInlineField> createState() => _BondInlineFieldState();
}

class _BondInlineFieldState extends State<BondInlineField> {
  late final TextEditingController _controller =
      TextEditingController(text: widget.value);
  late final FocusNode _focus = FocusNode()..addListener(_onFocus);
  String? _lastCommitted;

  @override
  void didUpdateWidget(BondInlineField old) {
    super.didUpdateWidget(old);
    if (widget.value != old.value) {
      // Follow the outside value unless the person is mid-edit: a field that
      // still shows what was just committed (an answer or a rollback arrived)
      // follows too, even while it keeps focus after Enter.
      final justCommitted =
          _lastCommitted != null && _controller.text.trim() == _lastCommitted;
      if (!_focus.hasFocus || justCommitted) _controller.text = widget.value;
    }
  }

  @override
  void dispose() {
    _focus.removeListener(_onFocus);
    _focus.dispose();
    _controller.dispose();
    super.dispose();
  }

  void _onFocus() {
    if (!_focus.hasFocus) _commit();
  }

  void _commit() {
    final text = _controller.text.trim();
    if (text == widget.value.trim() || text == _lastCommitted) return;
    _lastCommitted = text;
    widget.onCommit(text);
  }

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    // Not editing and showing something other than the value (a rollback
    // landed while the field kept the typed text): follow the value.
    if (!_focus.hasFocus && _controller.text != widget.value) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && !_focus.hasFocus && _controller.text != widget.value) {
          _controller.text = widget.value;
        }
      });
    }
    final field = bondSemantics(
      id: widget.semanticsId,
      label: widget.semanticLabel,
      textField: true,
      child: TextField(
        controller: _controller,
        focusNode: _focus,
        enabled: widget.enabled,
        maxLines: widget.maxLines,
        textAlign: widget.textAlign,
        keyboardType: widget.keyboardType,
        inputFormatters: widget.keyboardType == TextInputType.number
            ? [FilteringTextInputFormatter.allow(RegExp(r'[0-9.,$]'))]
            : null,
        onChanged: (_) => _lastCommitted = null,
        onSubmitted: (_) => _commit(),
        style: BondText(t).style(BondText.small14, BondText.medium),
        decoration: InputDecoration(
          isDense: true,
          hintText: widget.hint,
          suffixText: widget.suffix,
          contentPadding: const EdgeInsets.symmetric(
              horizontal: BondSpace.s8, vertical: BondSpace.s8),
        ),
      ),
    );
    return widget.width == null
        ? field
        : SizedBox(width: widget.width, child: field);
  }
}
