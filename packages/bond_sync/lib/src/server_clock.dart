/// The server's clock as the device best knows it: its own clock plus the
/// offset taken from the latest `server_now`.
library;

/// No state management and no storage: the app persists the offset itself
/// through [onOffset] and [restore].
class ServerClock {
  ServerClock([DateTime Function()? phoneNow, Duration offset = Duration.zero, this.onOffset])
      : _phoneNow = phoneNow ?? DateTime.now,
        _offset = offset;

  final DateTime Function() _phoneNow;
  Duration _offset;

  /// Called after every new offset so the host can keep it for the next launch.
  final void Function(Duration offset)? onOffset;

  /// Server minus device.
  Duration get offset => _offset;

  /// Same as [offset]: how far the device clock is behind (positive) or ahead (negative).
  Duration get skew => _offset;

  /// The device's own clock, uncorrected.
  DateTime phoneNow() => _phoneNow();

  /// The server's time now. Use this for every stamp a person sees.
  DateTime now() => _phoneNow().add(_offset);

  /// Sets the offset without telling [onOffset] (restoring the last run's value).
  void restore(Duration offset) => _offset = offset;

  /// Records the offset from a `server_now` stamp.
  void note(DateTime serverNow) {
    _offset = serverNow.difference(_phoneNow());
    onOffset?.call(_offset);
  }
}
