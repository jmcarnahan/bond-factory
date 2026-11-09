import 'package:flutter/material.dart';

import '../tokens/tokens.dart';

/// One row of a timeline: when, what, and the line under it. A null [tone] is
/// a plain row; a tone colours its dot, and [BondToneRole.danger] also the title.
class BondTimelineItem {
  const BondTimelineItem({required this.timeLabel, required this.title, this.body, this.tone});

  final String timeLabel;
  final String title;
  final String? body;
  final BondToneRole? tone;
}

/// A vertical timeline: time on the left, a tone dot, then the title and its
/// detail. A danger row is the one that needs the person.
class BondTimelineList extends StatelessWidget {
  const BondTimelineList({super.key, required this.items});

  final List<BondTimelineItem> items;

  static const double _timeLane = 72;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final text = BondText(t);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (var i = 0; i < items.length; i++)
          Padding(
            key: ValueKey('bond-timeline-$i'),
            padding: const EdgeInsets.symmetric(vertical: BondSpace.s8),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SizedBox(width: _timeLane, child: Text(items[i].timeLabel, style: text.label)),
                Padding(
                  padding: const EdgeInsets.only(top: BondSpace.s4),
                  child: Container(
                    width: BondLayout.dot,
                    height: BondLayout.dot,
                    decoration: BoxDecoration(
                      color: items[i].tone == null ? t.lineStrong : t.tone(items[i].tone!).base,
                      shape: BoxShape.circle,
                    ),
                  ),
                ),
                BondSpace.w12,
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        items[i].title,
                        style: text.style(BondText.small14, BondText.semibold,
                            color: items[i].tone == BondToneRole.danger ? t.danger.press : t.ink),
                      ),
                      if (items[i].body != null && items[i].body!.isNotEmpty) Text(items[i].body!, style: text.small),
                    ],
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}
