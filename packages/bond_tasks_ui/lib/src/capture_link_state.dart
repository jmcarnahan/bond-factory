import 'package:bond_tasks/bond_tasks.dart';

class CaptureLinkState {
  CaptureLinkState(LinkCandidate l)
      : text = l.text,
        kind = l.kind,
        options = [...l.candidates],
        selected = l.candidates.isEmpty ? -1 : 0;

  final String text;
  final String kind;
  final List<LinkOption> options;

  /// Index into [options], or -1 for no match.
  int selected;

  LinkCandidate? get result {
    if (selected < 0 || selected >= options.length) return null;
    final chosen = options[selected];
    return LinkCandidate(
      text: text,
      kind: kind,
      candidates: [chosen, for (final o in options) if (o != chosen) o],
    );
  }

  LinkCandidate get view => LinkCandidate(text: text, kind: kind, candidates: options);
}
