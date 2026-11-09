import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/widgets.dart';

/// Reports what the person just did; the page shows it under `sdk.ui.last-event`.
typedef UiSay = void Function(String event);

/// A titled group of tiles on the UI page. The heading is found by
/// `sdk.ui.section-<id>`.
class UiSection extends StatelessWidget {
  const UiSection({super.key, required this.id, required this.title, required this.children});

  final String id;
  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final text = BondText.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 8),
        Semantics(
          identifier: 'sdk.ui.section-$id',
          header: true,
          child: Text(title, style: text.title),
        ),
        const SizedBox(height: 16),
        ...children,
      ],
    );
  }
}

/// One widget on show: its name above it, and the semantics id `sdk.ui.<name>`.
///
/// A widget that takes a `semanticsId` wears the id itself (pass the same
/// `sdk.ui.<name>` to it and leave [selfIdentified] true). One that does not
/// is wrapped here so a driver can still find its tile.
class UiTile extends StatelessWidget {
  const UiTile({super.key, required this.name, required this.child, this.selfIdentified = true});

  final String name;
  final Widget child;
  final bool selfIdentified;

  /// The identifier of the tile named [name].
  static String idOf(String name) => 'sdk.ui.$name';

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final body = selfIdentified
        ? child
        : Semantics(identifier: idOf(name), container: true, child: child);
    return Padding(
      padding: const EdgeInsets.only(bottom: 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(name, style: BondText.of(context).label.copyWith(color: t.muted)),
          const SizedBox(height: 8),
          body,
        ],
      ),
    );
  }
}

/// A fixed-width widget (a side navigation, a rail) that scrolls sideways
/// instead of overflowing on a phone.
class UiSideScroll extends StatelessWidget {
  const UiSideScroll({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) => SingleChildScrollView(scrollDirection: Axis.horizontal, child: child);
}

/// Small spacing between demo items in a [Wrap].
const double uiGap = 8;
