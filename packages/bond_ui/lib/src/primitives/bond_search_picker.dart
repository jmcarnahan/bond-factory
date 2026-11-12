import 'dart:async';

import 'package:flutter/material.dart';

import '../labels.dart';
import '../semantics.dart';
import '../tokens/tokens.dart';
import 'bond_chip.dart';
import 'bond_pressable.dart';
import 'bond_text_field.dart';

/// Pick items by searching. The picked items show as removable chips above a
/// search field; the results show as an inline list below it (no overlay).
/// [onSearch] runs after [debounce] once the text has [minChars] characters;
/// an answer that arrives after a newer search started is dropped. A busy
/// line, an empty line and an error line show inline.
///
/// With [semanticsId]: `<id>` the field, `<id>-picked-<n>` a chip,
/// `<id>-result-<n>` a result.
class BondSearchPicker<T> extends StatefulWidget {
  const BondSearchPicker({
    super.key,
    required this.onSearch,
    required this.labelOf,
    required this.onPick,
    this.picked = const [],
    this.onRemove,
    this.hint,
    this.semanticsId,
    this.minChars = 2,
    this.debounce = const Duration(milliseconds: 250),
  });

  final Future<List<T>> Function(String query) onSearch;
  final String Function(T item) labelOf;
  final void Function(T item) onPick;
  final List<T> picked;
  final void Function(T item)? onRemove;
  final String? hint;
  final String? semanticsId;
  final int minChars;
  final Duration debounce;

  @override
  State<BondSearchPicker<T>> createState() => _BondSearchPickerState<T>();
}

class _BondSearchPickerState<T> extends State<BondSearchPicker<T>> {
  final _controller = TextEditingController();
  Timer? _timer;
  int _seq = 0;
  List<T>? _results;
  bool _busy = false;
  bool _failed = false;

  @override
  void dispose() {
    _timer?.cancel();
    _controller.dispose();
    super.dispose();
  }

  void _changed(String text) {
    _timer?.cancel();
    final q = text.trim();
    _seq++;
    if (q.length < widget.minChars) {
      setState(() {
        _results = null;
        _busy = false;
        _failed = false;
      });
      return;
    }
    setState(() => _busy = true);
    final mine = _seq;
    _timer = Timer(widget.debounce, () => _run(q, mine));
  }

  Future<void> _run(String q, int mine) async {
    try {
      final found = await widget.onSearch(q);
      if (!mounted || mine != _seq) return;
      setState(() {
        _results = found;
        _busy = false;
        _failed = false;
      });
    } catch (_) {
      if (!mounted || mine != _seq) return;
      setState(() {
        _results = null;
        _busy = false;
        _failed = true;
      });
    }
  }

  void _pick(T item) {
    widget.onPick(item);
    _controller.clear();
    _seq++;
    setState(() {
      _results = null;
      _busy = false;
      _failed = false;
    });
  }

  String? _id(String part) => widget.semanticsId == null ? null : bondSemanticsOption(widget.semanticsId!, part);

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final text = BondText(t);
    final labels = BondLabels.of(context);
    final shown = [
      for (final r in _results ?? <T>[])
        if (!widget.picked.contains(r)) r,
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        if (widget.picked.isNotEmpty) ...[
          Wrap(
            spacing: BondSpace.s8,
            runSpacing: BondSpace.s8,
            children: [
              for (var i = 0; i < widget.picked.length; i++)
                _pickedChip(widget.picked[i], i, t, labels),
            ],
          ),
          BondSpace.h8,
        ],
        BondSearchField(
          controller: _controller,
          hint: widget.hint ?? labels.search,
          onChanged: _changed,
          semanticsId: widget.semanticsId,
        ),
        if (_busy) _line(text.small.copyWith(color: t.muted), labels.searching),
        if (_failed) _line(text.small.copyWith(color: t.danger.press), labels.searchFailed),
        if (!_busy && !_failed && _results != null && shown.isEmpty)
          _line(text.small.copyWith(color: t.muted), labels.noResults),
        if (!_busy && !_failed)
          for (var i = 0; i < shown.length; i++)
            BondPressable(
              onTap: () => _pick(shown[i]),
              semanticLabel: widget.labelOf(shown[i]),
              semanticsId: _id('result-$i'),
              minSize: BondLayout.controlSm,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: BondSpace.s12, vertical: BondSpace.s8),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: Text(widget.labelOf(shown[i]), style: text.body),
                ),
              ),
            ),
      ],
    );
  }

  /// A picked item. With [BondSearchPicker.onRemove] activating it removes the
  /// item, and its spoken label says so ("Remove: Ann").
  Widget _pickedChip(T item, int i, BondTokens t, BondLabels labels) {
    final name = widget.labelOf(item);
    final remove = widget.onRemove;
    final chip = BondChip(
      label: name,
      leading: Icon(Icons.close, size: BondLayout.icon, color: t.muted),
      onTap: remove == null ? null : () => remove(item),
      semanticsId: remove == null ? _id('picked-$i') : null,
    );
    if (remove == null) return chip;
    return Semantics(
      identifier: _id('picked-$i'),
      label: '${labels.remove}: $name',
      button: true,
      container: true,
      excludeSemantics: true,
      onTap: () => remove(item),
      child: chip,
    );
  }

  Widget _line(TextStyle style, String s) => Padding(
        padding: const EdgeInsets.only(top: BondSpace.s8),
        child: Text(s, style: style),
      );
}
