/// Picks the return address for a native sign-in.
///
/// An https return (universal or app link) is the safe default, but the
/// plugin only honours it on iOS 17.4 and later; below that it silently waits
/// for a scheme `https` that never arrives. The SDK never reads the platform,
/// so the app says whether this device can do https and gets the right one.
abstract final class NativeReturn {
  /// [httpsReturn] when [httpsSupported], else [schemeReturn] (a device-bound
  /// reverse-domain scheme the server lists in `native_schemes`). Throws
  /// [StateError] when a scheme is needed and none was given.
  static Uri choose({required Uri httpsReturn, Uri? schemeReturn, required bool httpsSupported}) {
    if (httpsSupported) return httpsReturn;
    if (schemeReturn == null) {
      throw StateError('This device cannot use an https return and no scheme return was given.');
    }
    return schemeReturn;
  }
}
