/// Outside a browser there is no window to send anywhere: the page shows the
/// address instead. Returns false to say nothing was navigated.
bool navigateTopLevel(Uri url) => false;

/// There is no address bar outside a browser: nothing to replace. Null means no failure.
String? replaceAddress(Uri url) => null;
