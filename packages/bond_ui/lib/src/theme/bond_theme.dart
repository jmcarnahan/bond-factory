import 'package:flutter/material.dart';

import '../tokens/tokens.dart';

/// Material 3 theme built from [BondTokens]. Deliberately sets no theme for
/// tooltips, snack bars, dialogs, sheets or popup menus: shared widgets show
/// state inline.
abstract final class BondTheme {
  static ThemeData build(
    BondTokens tokens, {
    Brightness brightness = Brightness.light,
  }) {
    final scheme = ColorScheme(
      brightness: brightness,
      primary: tokens.accent.base,
      onPrimary: tokens.onFill,
      secondary: tokens.ink,
      onSecondary: tokens.surface,
      error: tokens.danger.press,
      onError: tokens.onFill,
      surface: tokens.surface,
      onSurface: tokens.ink,
      outline: tokens.lineStrong,
      outlineVariant: tokens.line,
    );
    final text = BondText(tokens);

    OutlineInputBorder border(Color color, double width) => OutlineInputBorder(
          borderRadius: tokens.shape.r12All,
          borderSide: BorderSide(color: color, width: width),
        );

    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: scheme,
      fontFamily: tokens.fontFamily,
      package: tokens.fontPackage,
      scaffoldBackgroundColor: tokens.ground,
      canvasColor: tokens.ground,
      dividerColor: tokens.line,
      splashFactory: InkRipple.splashFactory,
      textTheme: BondText.textTheme(tokens),
      extensions: <ThemeExtension<dynamic>>[tokens],
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: tokens.surface,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: BondSpace.s12,
          vertical: BondSpace.s12,
        ),
        hintStyle: text.style(BondText.base16, BondText.regular,
            color: tokens.muted),
        border: border(tokens.lineStrong, BondLayout.hairline),
        enabledBorder: border(tokens.lineStrong, BondLayout.hairline),
        focusedBorder: border(tokens.accent.base, BondLayout.rule),
        errorBorder: border(tokens.danger.press, BondLayout.hairline),
        focusedErrorBorder: border(tokens.danger.press, BondLayout.rule),
      ),
      textSelectionTheme: TextSelectionThemeData(
        cursorColor: tokens.accent.base,
        selectionColor: tokens.accent.soft,
      ),
      cardTheme: CardThemeData(
        color: tokens.surface,
        elevation: 0,
        margin: EdgeInsets.zero,
      ),
      dividerTheme: DividerThemeData(
        color: tokens.line,
        space: BondLayout.hairline,
        thickness: BondLayout.hairline,
      ),
    );
  }
}
