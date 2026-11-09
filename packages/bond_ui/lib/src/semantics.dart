import 'package:flutter/widgets.dart';

/// Wraps [child] in `Semantics(identifier: id, label: label)`. Every
/// interactive bond widget calls this with its `semanticsId`; with no id,
/// label or flags it returns [child] unchanged.
///
/// A [button] (or a node with an [id]) is its own semantics node, so a screen
/// reader never merges it into the text beside it. With [excludeChildren] the
/// inner widgets are hidden and this node carries [onTap] itself.
Widget bondSemantics({
  required String? id,
  String? label,
  bool button = false,
  bool? enabled,
  bool? selected,
  bool? toggled,
  bool? expanded,
  bool? textField,
  VoidCallback? onTap,
  bool excludeChildren = false,
  bool explicitChildNodes = false,
  required Widget child,
}) {
  final plain = id == null &&
      label == null &&
      !button &&
      enabled == null &&
      selected == null &&
      toggled == null &&
      expanded == null &&
      textField == null;
  if (plain) return child;
  return Semantics(
    identifier: id,
    label: label,
    button: button,
    enabled: enabled,
    selected: selected,
    toggled: toggled,
    expanded: expanded,
    textField: textField,
    onTap: onTap,
    container: button || id != null || explicitChildNodes,
    explicitChildNodes: explicitChildNodes,
    child: excludeChildren ? ExcludeSemantics(child: child) : child,
  );
}

/// Identifier for one option of a group: `'$id-$value'`.
String bondSemanticsOption(String id, String value) => '$id-$value';
