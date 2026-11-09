import 'package:flutter/widgets.dart';

/// Width class of the current window.
enum BondSize { phone, tablet, desktop }

/// Fixed layout numbers plus the only legal place to compare a width.
@immutable
class BondLayout {
  const BondLayout(this.width);

  /// Layout for a given [width].
  factory BondLayout.forWidth(double width) => BondLayout(width);

  /// Layout for the window containing [context].
  factory BondLayout.of(BuildContext context) =>
      BondLayout(MediaQuery.sizeOf(context).width);

  final double width;

  // Breakpoints.
  /// Below this width a screen is one column (phone, small tablet).
  static const double tabletFrom = 720;

  /// At or above this width the full desktop layout is shown.
  static const double desktopFrom = 1100;

  BondSize get size => width < tabletFrom
      ? BondSize.phone
      : (width < desktopFrom ? BondSize.tablet : BondSize.desktop);

  bool get isPhone => size == BondSize.phone;
  bool get isTablet => size == BondSize.tablet;
  bool get isDesktop => size == BondSize.desktop;

  /// Page padding for this width.
  EdgeInsets get pagePadding => isPhone
      ? const EdgeInsets.symmetric(horizontal: 16, vertical: 16)
      : const EdgeInsets.symmetric(horizontal: 32, vertical: 24);

  // Content widths.
  static const double contentMaxWidth = 1208;

  /// A single-column form on a wide page.
  static const double formMaxWidth = 560;
  static const double railWidth = 360;
  static const double sidebar = 232;

  /// Sidebar collapsed to icons.
  static const double sidebarRail = 72;
  static const double phoneWidth = 390;

  // Line weights.
  static const double hairline = 1;
  static const double rule = 2;

  // Controls.
  static const double minTap = 48;
  static const double control = 44;
  static const double controlSm = 36;
  static const double iconSm = 16;
  static const double icon = 20;
  static const double iconLg = 24;

  // Rows.
  static const double leadingLane = 40;
  static const double trailingLane = 120;
  static const double avatarSm = 32;
  static const double avatar = 40;
  static const double avatarLg = 64;
  static const double dot = 10;
  static const double dashLength = 4;
  static const double photoAspect = 1.6;
  static const double calendarCell = 40;

  @override
  bool operator ==(Object other) =>
      other is BondLayout && other.width == width;

  @override
  int get hashCode => width.hashCode;
}
