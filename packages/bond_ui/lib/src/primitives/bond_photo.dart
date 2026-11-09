import 'package:flutter/material.dart';

import '../tokens/tokens.dart';

/// A rounded photo from a URL with a quiet placeholder while it loads or when
/// there is no image. It only displays; nothing is written to our own
/// storage.
class BondPhoto extends StatelessWidget {
  const BondPhoto({
    super.key,
    required this.url,
    this.width,
    this.height,
    this.radius = BondRadius.r12All,
    this.icon = Icons.image_outlined,
    this.semanticLabel,
    this.headers,
  });

  final String? url;
  final double? width;
  final double? height;
  final BorderRadius radius;
  final IconData icon;
  final String? semanticLabel;

  /// Request headers for the image fetch (a bearer token for private photos).
  final Map<String, String>? headers;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    Widget placeholder() => Container(
          width: width,
          height: height,
          color: t.line,
          alignment: Alignment.center,
          child: Icon(icon, size: BondLayout.iconLg, color: t.lineStrong),
        );
    final u = url;
    final Widget body = (u == null || u.isEmpty)
        ? placeholder()
        : Image.network(
            u,
            width: width,
            height: height,
            headers: headers,
            fit: BoxFit.cover,
            semanticLabel: semanticLabel,
            loadingBuilder: (context, child, progress) =>
                progress == null ? child : placeholder(),
            errorBuilder: (context, error, stack) => placeholder(),
          );
    return ClipRRect(borderRadius: radius, child: body);
  }
}
