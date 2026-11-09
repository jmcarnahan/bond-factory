import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../semantics.dart';
import '../tokens/tokens.dart';

/// A labelled text input. The label is always visible above the field and a
/// validation message ([errorText]) shows inline under it.
class BondTextField extends StatelessWidget {
  const BondTextField({
    super.key,
    this.controller,
    this.label,
    this.hint,
    this.errorText,
    this.onChanged,
    this.onSubmitted,
    this.focusNode,
    this.keyboardType,
    this.maxLines = 1,
    this.maxLength,
    this.obscureText = false,
    this.prefix,
    this.enabled = true,
    this.autofocus = false,
    this.autofillHints,
    this.textInputAction,
    this.inputFormatters,
    this.textAlign = TextAlign.start,
    this.focusColor,
    this.semanticsId,
  });

  final TextEditingController? controller;
  final String? label;
  final String? hint;
  final String? errorText;
  final ValueChanged<String>? onChanged;
  final ValueChanged<String>? onSubmitted;
  final FocusNode? focusNode;
  final TextInputType? keyboardType;
  final int maxLines;

  /// Shows an "n/max" counter. Typing past it is allowed (a paste is never
  /// cut silently); the screen turns Save off and says so.
  final int? maxLength;
  final bool obscureText;
  final Widget? prefix;
  final bool enabled;
  final bool autofocus;

  /// For password managers: `AutofillHints.email`, `AutofillHints.password`.
  final Iterable<String>? autofillHints;
  final TextInputAction? textInputAction;
  final List<TextInputFormatter>? inputFormatters;
  final TextAlign textAlign;

  /// The focus ring's colour; null keeps the theme's accent.
  final Color? focusColor;
  final String? semanticsId;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final text = BondText(t);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        if (label != null) ...[
          // The field below carries this label for a screen reader.
          ExcludeSemantics(
              child: Text(label!,
                  style: text.style(BondText.small14, BondText.semibold))),
          BondSpace.h4,
        ],
        // One semantics node for the field: a plain wrapper beside the
        // editable gives Flutter web two text boxes.
        MergeSemantics(
          child: bondSemantics(
            id: semanticsId,
            label: label,
            textField: true,
            child: TextField(
              controller: controller,
              focusNode: focusNode,
              onChanged: onChanged,
              onSubmitted: onSubmitted,
              keyboardType: keyboardType,
              maxLines: maxLines,
              maxLength: maxLength,
              maxLengthEnforcement: MaxLengthEnforcement.none,
              // Drawn but kept out of the merged node, so the field's label
              // stays its label. The limit is visual only: the counter turns
              // to the danger tone past it.
              buildCounter: maxLength == null
                  ? null
                  : (context,
                          {required currentLength,
                          required isFocused,
                          required maxLength}) =>
                      _counter(t, currentLength, maxLength),
              obscureText: obscureText,
              enabled: enabled,
              autofocus: autofocus,
              autofillHints: autofillHints,
              textInputAction: textInputAction,
              inputFormatters: inputFormatters,
              textAlign: textAlign,
              style: text.style(BondText.base16, BondText.regular),
              decoration: InputDecoration(
                hintText: hint,
                // A hint wraps (and the field grows) rather than being cut.
                hintMaxLines: 2,
                errorText: errorText,
                prefixIcon: prefix,
                focusedBorder: bondFocusedBorder(focusColor),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

/// The theme's focused border shape in [color]; null defers to the theme.
InputBorder? bondFocusedBorder(Color? color) => color == null
    ? null
    : OutlineInputBorder(
        borderRadius: BondRadius.r12All,
        borderSide: BorderSide(color: color, width: BondLayout.rule),
      );

Widget _counter(BondTokens t, int currentLength, int? maxLength) {
  final over = maxLength != null && currentLength > maxLength;
  return ExcludeSemantics(
    child: Text(
      '$currentLength/$maxLength',
      style: BondText(t).style(BondText.small14, BondText.regular,
          color: over ? t.danger.base : t.muted),
    ),
  );
}

/// A search input with a leading magnifier.
class BondSearchField extends StatelessWidget {
  const BondSearchField({
    super.key,
    this.controller,
    this.hint,
    this.onChanged,
    this.onSubmitted,
    this.focusNode,
    this.trailing,
    this.semanticLabel,
    this.semanticsId,
    this.icon = Icons.search,
    this.textInputAction,
    this.focusColor,
  });

  final IconData icon;
  final TextEditingController? controller;
  final String? hint;
  final ValueChanged<String>? onChanged;
  final ValueChanged<String>? onSubmitted;
  final FocusNode? focusNode;
  final Widget? trailing;
  final String? semanticLabel;
  final String? semanticsId;

  /// The keyboard's action key (default search; submitting also closes the
  /// keyboard).
  final TextInputAction? textInputAction;

  /// The focus ring's colour; null keeps the theme's accent.
  final Color? focusColor;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    return bondSemantics(
      id: semanticsId,
      textField: true,
      label: semanticLabel ?? hint,
      child: TextField(
        controller: controller,
        focusNode: focusNode,
        onChanged: onChanged,
        onSubmitted: (v) {
          onSubmitted?.call(v);
          FocusManager.instance.primaryFocus?.unfocus();
        },
        textInputAction: textInputAction ?? TextInputAction.search,
        style: BondText(t).style(BondText.base16, BondText.regular),
        decoration: InputDecoration(
          hintText: hint,
          prefixIcon: Icon(icon, size: BondLayout.icon, color: t.muted),
          suffixIcon: trailing,
          focusedBorder: bondFocusedBorder(focusColor),
        ),
      ),
    );
  }
}
