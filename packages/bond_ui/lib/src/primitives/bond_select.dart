import 'package:flutter/material.dart';

import '../labels.dart';
import '../semantics.dart';
import '../tokens/tokens.dart';
import 'bond_chip.dart';
import 'bond_pressable.dart';
import 'bond_segmented.dart';

/// How a [BondSelect] shows its options. Every variant is inline: nothing
/// opens over the page.
enum BondSelectVariant {
  /// A wrapping row of chips.
  chips,

  /// A segmented control (needs a non-null value).
  segmented,

  /// A column of radio rows, optionally filterable.
  radioList,

  /// A field that shows the chosen option and expands the radio list in the
  /// page flow when tapped. For long, flat lists.
  expanding,
}

class BondOption<T> {
  const BondOption(this.value, this.label);

  final T value;
  final String label;
}

/// Pick one of a list of options. With [semanticsId], each option is
/// identified as `'<id>-<value>'` and the expanding header as the id itself.
class BondSelect<T> extends StatefulWidget {
  const BondSelect({
    super.key,
    required this.options,
    required this.value,
    required this.onChanged,
    this.variant = BondSelectVariant.chips,
    this.label,
    this.searchable = false,
    this.searchHint,
    this.placeholder,
    this.semanticsId,
  });

  final List<BondOption<T>> options;
  final T? value;
  final ValueChanged<T> onChanged;
  final BondSelectVariant variant;
  final String? label;

  /// Radio list and expanding variants: shows a filter box above the list.
  final bool searchable;
  final String? searchHint;

  /// Expanding variant: text while nothing is chosen (defaults to the
  /// `select` label).
  final String? placeholder;
  final String? semanticsId;

  @override
  State<BondSelect<T>> createState() => _BondSelectState<T>();
}

class _BondSelectState<T> extends State<BondSelect<T>> {
  String _query = '';
  bool _open = false;

  String? _optionId(T value) => widget.semanticsId == null
      ? null
      : bondSemanticsOption(widget.semanticsId!, '$value');

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final body = switch (widget.variant) {
      BondSelectVariant.chips => Wrap(
          spacing: BondSpace.s8,
          runSpacing: BondSpace.s8,
          children: [
            for (final o in widget.options)
              BondChip(
                label: o.label,
                selected: o.value == widget.value,
                onTap: () => widget.onChanged(o.value),
                semanticsId: _optionId(o.value),
              ),
          ],
        ),
      BondSelectVariant.segmented => BondSegmented<T>(
          segments: [
            for (final o in widget.options) BondSegment(o.value, o.label),
          ],
          value: widget.value as T,
          onChanged: widget.onChanged,
          semanticsId: widget.semanticsId,
        ),
      BondSelectVariant.radioList => _radioList(t),
      BondSelectVariant.expanding => _expanding(t),
    };
    if (widget.label == null) return body;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(widget.label!,
            style: BondText(t).style(BondText.small14, BondText.semibold)),
        BondSpace.h8,
        body,
      ],
    );
  }

  Widget _radioList(BondTokens t, {bool collapseOnPick = false}) {
    final shown = widget.options
        .where((o) => o.label.toLowerCase().contains(_query.toLowerCase()))
        .toList();
    final labels = BondLabels.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        if (widget.searchable) ...[
          TextField(
            onChanged: (v) => setState(() => _query = v),
            decoration: InputDecoration(
              hintText: widget.searchHint ?? labels.search,
              prefixIcon: const Icon(Icons.search, size: BondLayout.icon),
            ),
          ),
          BondSpace.h8,
        ],
        if (shown.isEmpty)
          Padding(
            padding: BondSpace.all12,
            child: Text(labels.noResults, style: BondText(t).small),
          ),
        for (final o in shown)
          bondSemantics(
            id: _optionId(o.value),
            label: o.label,
            button: true,
            selected: o.value == widget.value,
            onTap: () => _pick(o.value, collapseOnPick),
            excludeChildren: true,
            child: BondPressable(
              onTap: () => _pick(o.value, collapseOnPick),
              borderRadius: BondRadius.r8All,
              minSize: BondLayout.minTap,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: BondSpace.s8),
                child: Row(
                  children: [
                    Icon(
                      o.value == widget.value
                          ? Icons.radio_button_checked
                          : Icons.radio_button_unchecked,
                      size: BondLayout.icon,
                      color:
                          o.value == widget.value ? t.accent.base : t.muted,
                    ),
                    BondSpace.w12,
                    Expanded(child: Text(o.label, style: BondText(t).body)),
                  ],
                ),
              ),
            ),
          ),
      ],
    );
  }

  void _pick(T value, bool collapse) {
    if (collapse) {
      setState(() {
        _open = false;
        _query = '';
      });
    }
    widget.onChanged(value);
  }

  Widget _expanding(BondTokens t) {
    final labels = BondLabels.of(context);
    String? current;
    for (final o in widget.options) {
      if (o.value == widget.value) current = o.label;
    }
    final text = BondText(t);
    return Container(
      decoration: BoxDecoration(
        color: t.surface,
        borderRadius: BondRadius.r12All,
        border: Border.all(color: t.lineStrong),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          bondSemantics(
            id: widget.semanticsId,
            label: current ?? widget.placeholder ?? labels.select,
            button: true,
            toggled: _open,
            onTap: () => setState(() => _open = !_open),
            excludeChildren: true,
            child: BondPressable(
              onTap: () => setState(() => _open = !_open),
              borderRadius: BondRadius.r12All,
              minSize: BondLayout.control,
              child: Padding(
                padding: const EdgeInsets.symmetric(
                    horizontal: BondSpace.s12, vertical: BondSpace.s8),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        current ?? widget.placeholder ?? labels.select,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: current == null
                            ? text.style(BondText.base16, BondText.regular,
                                color: t.muted)
                            : text.body,
                      ),
                    ),
                    Icon(_open ? Icons.expand_less : Icons.expand_more,
                        size: BondLayout.iconLg, color: t.muted),
                  ],
                ),
              ),
            ),
          ),
          if (_open)
            Padding(
              padding: const EdgeInsets.fromLTRB(
                  BondSpace.s8, 0, BondSpace.s8, BondSpace.s8),
              child: _radioList(t, collapseOnPick: true),
            ),
        ],
      ),
    );
  }
}
