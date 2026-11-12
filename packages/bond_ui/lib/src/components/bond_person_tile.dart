import 'package:flutter/material.dart';

import '../primitives/bond_avatar.dart';
import '../primitives/bond_list_row.dart';

/// A person as a list row: initials avatar, name, a subtitle and a trailing
/// widget. Built on [BondListRow]; [onTap] makes the row tappable.
class BondPersonTile extends StatelessWidget {
  const BondPersonTile({
    super.key,
    required this.name,
    this.subtitle,
    this.initials,
    this.trailing,
    this.onTap,
    this.semanticsId,
  });

  final String name;
  final String? subtitle;

  /// Defaults to the first letters of the first two words of [name].
  final String? initials;
  final Widget? trailing;
  final VoidCallback? onTap;
  final String? semanticsId;

  static String initialsOf(String name) {
    final parts = name.trim().split(RegExp(r'\s+')).where((p) => p.isNotEmpty).toList();
    if (parts.isEmpty) return '?';
    return parts.take(2).map((p) => p.substring(0, 1).toUpperCase()).join();
  }

  @override
  Widget build(BuildContext context) => BondListRow(
        title: name,
        subtitle: subtitle,
        leading: BondAvatar(initials: initials ?? initialsOf(name)),
        trailing: trailing,
        onTap: onTap,
        semanticsId: semanticsId,
      );
}
