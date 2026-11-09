import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../semantics.dart';
import '../tokens/tokens.dart';
import 'bond_pressable.dart';

class BondSegment<T> {
  const BondSegment(this.value, this.label);

  final T value;
  final String label;
}

/// A row of mutually exclusive choices, always visible (EN / ES, Today /
/// Tomorrow, Day / Week / Month). With [semanticsId], each cell is identified
/// as `'<id>-<value>'`.
class BondSegmented<T> extends StatelessWidget {
  const BondSegmented({
    super.key,
    required this.segments,
    required this.value,
    required this.onChanged,
    this.expand = false,
    this.semanticsId,
  });

  final List<BondSegment<T>> segments;
  final T value;
  final ValueChanged<T> onChanged;
  final bool expand;
  final String? semanticsId;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final items = [
      for (final s in segments)
        _Cell<T>(
          segment: s,
          selected: s.value == value,
          onTap: () => onChanged(s.value),
          semanticsId: semanticsId == null
              ? null
              : bondSemanticsOption(semanticsId!, '${s.value}'),
        ),
    ];
    final scaler = MediaQuery.textScalerOf(context);
    final direction = Directionality.maybeOf(context) ?? TextDirection.ltr;
    return LayoutBuilder(
      builder: (context, constraints) {
        // Labels never break inside a word. When they do not all fit on one
        // line, whole pills wrap to the next line instead.
        final wrap = constraints.hasBoundedWidth &&
            _widestRow(t, scaler, direction) > constraints.maxWidth;
        return Container(
          padding: BondSpace.all4,
          decoration: BoxDecoration(
            color: t.line,
            borderRadius: BondRadius.r12All,
          ),
          child: wrap
              ? Wrap(children: items)
              : Row(
                  mainAxisSize: expand ? MainAxisSize.max : MainAxisSize.min,
                  children: [
                    for (final cell in items)
                      expand ? Expanded(child: cell) : cell,
                  ],
                ),
        );
      },
    );
  }

  /// The width the control needs to show every label whole on one row: the
  /// container padding plus the cells (equal cells when [expand] is set).
  double _widestRow(BondTokens t, TextScaler scaler, TextDirection direction) {
    var total = 0.0;
    var widest = 0.0;
    for (final s in segments) {
      final painter = TextPainter(
        text: TextSpan(
            text: s.label, style: _Cell.labelStyle(t, selected: true)),
        textDirection: direction,
        textScaler: scaler,
        maxLines: 1,
      )..layout();
      final cell = math.max(BondLayout.minTap, painter.width + 2 * BondSpace.s12);
      painter.dispose();
      total += cell;
      widest = math.max(widest, cell);
    }
    return 2 * BondSpace.s4 + (expand ? widest * segments.length : total);
  }
}

class _Cell<T> extends StatelessWidget {
  const _Cell({
    required this.segment,
    required this.selected,
    required this.onTap,
    required this.semanticsId,
  });

  final BondSegment<T> segment;
  final bool selected;
  final VoidCallback onTap;
  final String? semanticsId;

  /// The label's style; the selected weight is the widest.
  static TextStyle labelStyle(BondTokens t, {required bool selected}) =>
      BondText(t).style(
        BondText.small14,
        selected ? BondText.semibold : BondText.medium,
        color: selected ? t.ink : t.muted,
      );

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    return bondSemantics(
      id: semanticsId,
      button: true,
      selected: selected,
      label: segment.label,
      onTap: onTap,
      excludeChildren: true,
      child: BondPressable(
        onTap: onTap,
        borderRadius: BondRadius.r8All,
        color: selected ? t.surface : null,
        child: Container(
          constraints: const BoxConstraints(
            minHeight: BondLayout.controlSm,
            minWidth: BondLayout.minTap,
          ),
          padding: const EdgeInsets.symmetric(horizontal: BondSpace.s12),
          alignment: Alignment.center,
          child: Text(
            segment.label,
            softWrap: false,
            maxLines: 1,
            overflow: TextOverflow.visible,
            style: labelStyle(t, selected: selected),
          ),
        ),
      ),
    );
  }
}
