import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

/// One mention in a captured item ("with Dana") and its matches: the
/// alternatives are chips to choose between, inline, plus "No match". With
/// [linkSearch], a search shows while no match is chosen so the person can find
/// the record by hand. [selected] is an index into the candidates, or -1.
class BondCaptureLinkRow extends StatelessWidget {
  const BondCaptureLinkRow({
    super.key,
    required this.link,
    required this.selected,
    required this.onSelect,
    required this.onFound,
    this.linkSearch,
    this.labels = const CaptureLabels(),
    this.semanticsId,
  });

  final LinkCandidate link;
  final int selected;
  final ValueChanged<int> onSelect;

  /// A record found by the search: the card adds it as a candidate and picks it.
  final ValueChanged<LinkOption> onFound;
  final LinkSearch? linkSearch;
  final CaptureLabels labels;
  final String? semanticsId;

  String? _id(String part) => semanticsId == null ? null : '$semanticsId-$part';

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final text = BondText(t);
    final search = linkSearch;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          '${labels.linkTo}: ${link.text}',
          style: text.small.copyWith(color: t.muted),
        ),
        BondSpace.h4,
        Wrap(
          spacing: BondSpace.s8,
          runSpacing: BondSpace.s8,
          children: [
            for (var i = 0; i < link.candidates.length; i++)
              BondChip(
                label: link.candidates[i].label,
                selected: selected == i,
                onTap: () => onSelect(i),
                semanticsId: _id('option-$i'),
              ),
            BondChip(
              label: labels.noMatch,
              selected: selected < 0,
              onTap: () => onSelect(-1),
              semanticsId: _id('none'),
            ),
          ],
        ),
        if (search != null && selected < 0) ...[
          BondSpace.h8,
          BondSearchPicker<TaskLink>(
            onSearch: (q) => search.search(link.kind, q),
            labelOf: (l) => (l.label ?? '').isEmpty ? l.id : l.label!,
            onPick: (l) => onFound(LinkOption(id: l.id, label: (l.label ?? '').isEmpty ? l.id : l.label!)),
            hint: labels.searchLinkHint,
            semanticsId: _id('search'),
          ),
        ],
      ],
    );
  }
}
