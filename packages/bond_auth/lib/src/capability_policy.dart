/// Which capabilities a session grants.
library;

import 'session.dart';

abstract interface class CapabilityPolicy {
  bool has(AuthSession s, String cap);
}

/// A capability is held when the token's capability list names it. A session
/// holding any [superuser] capability holds every one.
class ClaimListPolicy implements CapabilityPolicy {
  const ClaimListPolicy({this.superuser = const {}});

  final Set<String> superuser;

  @override
  bool has(AuthSession s, String cap) {
    if (s.capabilities.contains(cap)) return true;
    return s.capabilities.any(superuser.contains);
  }
}
