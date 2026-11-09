import 'package:flutter/material.dart';

import '../primitives/bond_pressable.dart';
import '../semantics.dart';
import '../tokens/tokens.dart';

class BondColumn {
  const BondColumn(this.label, {this.flex = 1, this.width, this.alignEnd = false});

  final String label;
  final int flex;

  /// A fixed column width. When set, [flex] is ignored.
  final double? width;
  final bool alignEnd;
}

/// A table built from rows of widgets. Header labels and cells share the same
/// flex so columns line up. Given less than [stackBelow] of width (a phone) it
/// stacks each row into a card: one "label, value" line per column.
class BondTable extends StatelessWidget {
  const BondTable({
    super.key,
    required this.columns,
    required this.rows,
    this.onRowTap,
    this.rowTappable,
    this.emptyText,
    this.footer,
    this.uppercaseHeaders = true,
    this.stackBelow = 540,
    this.semanticsId,
  });

  final List<BondColumn> columns;
  final List<List<Widget>> rows;
  final ValueChanged<int>? onRowTap;

  /// Rows for which this returns false are plain: no hover, no tap.
  final bool Function(int row)? rowTappable;
  final String? emptyText;

  /// A row under the last data row, such as "Showing 8 of 1,912".
  final Widget? footer;
  final bool uppercaseHeaders;
  final double stackBelow;

  /// Rows that can be tapped are `<semanticsId>-row-<index>`.
  final String? semanticsId;

  bool _tappable(int r) => onRowTap != null && (rowTappable?.call(r) ?? true);

  Widget _row(int r, Widget content) {
    if (!_tappable(r)) return content;
    return bondSemantics(
      id: semanticsId == null ? null : '$semanticsId-row-$r',
      button: true,
      onTap: () => onRowTap!(r),
      child: BondPressable(onTap: () => onRowTap!(r), borderRadius: BorderRadius.zero, child: content),
    );
  }

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    return Container(
      decoration: BoxDecoration(
        color: t.surface,
        borderRadius: BondRadius.r16All,
        border: Border.all(color: t.line),
      ),
      clipBehavior: Clip.antiAlias,
      child: LayoutBuilder(
        builder: (context, box) {
          final stacked = box.maxWidth < stackBelow;
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: [
              if (!stacked) _header(context),
              if (rows.isEmpty && emptyText != null)
                Padding(
                  padding: BondSpace.all24,
                  child: Center(child: Text(emptyText!, style: BondText.of(context).small)),
                ),
              for (var r = 0; r < rows.length; r++) ...[
                if (!stacked || r > 0) Divider(height: 1, color: t.line),
                stacked ? _stackedRow(context, r) : _row(r, _line(rows[r])),
              ],
              if (footer != null) ...[Divider(height: 1, color: t.line), footer!],
            ],
          );
        },
      ),
    );
  }

  Widget _header(BuildContext context) {
    final t = BondTokens.of(context);
    return Container(
      color: t.ground,
      child: _line([
        for (final c in columns)
          Text(
            uppercaseHeaders ? c.label.toUpperCase() : c.label,
            style: uppercaseHeaders ? BondText.of(context).eyebrow : BondText.of(context).label,
          ),
      ]),
    );
  }

  Widget _line(List<Widget> cells) => Row(
        children: [
          for (var c = 0; c < columns.length; c++)
            () {
              final inner = Align(
                alignment: columns[c].alignEnd ? Alignment.centerRight : Alignment.centerLeft,
                child: Padding(
                  padding: const EdgeInsets.all(BondSpace.s12),
                  child: c < cells.length ? cells[c] : const SizedBox.shrink(),
                ),
              );
              final w = columns[c].width;
              return w != null ? SizedBox(width: w, child: inner) : Expanded(flex: columns[c].flex, child: inner);
            }(),
        ],
      );

  Widget _stackedRow(BuildContext context, int r) {
    final cells = rows[r];
    final content = Padding(
      padding: BondSpace.all12,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (var c = 0; c < columns.length && c < cells.length; c++)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: BondSpace.s4),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(width: 104, child: Text(columns[c].label, style: BondText.of(context).label)),
                  Expanded(
                    child: Align(
                      alignment: columns[c].alignEnd ? Alignment.centerRight : Alignment.centerLeft,
                      child: cells[c],
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
    return _row(r, content);
  }
}
