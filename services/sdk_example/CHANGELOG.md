# Changelog

## 0.1.0 - unreleased
- Scaffold.
- Connections: native-app flow (`start?mode=native`, cookie-less `/go` and callback for native states, `POST
  /connections/{provider}/redeem`); `SDK_EXAMPLE_NATIVE_REDIRECTS` (default `sdkdemo://connections`).
- Direct sign-in: `signin_wiring.py` (library objects, cookies, router and well-known mounts), `directory.py` (the
  `UserDirectory` over `users`), `scope_policy.py`; `users` gains `identity_provider`, `identity_subject` (unique pair)
  and `allow_password`; new tables `auth_sessions` and `oauth_handoffs` (migration `0003_signin`).
- `/auth/refresh`, `/auth/logout` and `/auth/providers` are now the library's; `/auth/firebase` is break-glass only
  (`SDK_EXAMPLE_BREAKGLASS=1`, rows with `allow_password`); `/auth/demo` and break-glass issue refresh sessions
  (`delivery: "body"` for phones); fake-mode `POST /auth/simulate-reuse`.
- Breaking: `GET /connections` answers `{connections, wanted}` (was a bare array); `start` takes `set`; a native
  `start` needs `device_challenge` and `redeem` needs `device_secret` (hand-offs live in `oauth_handoffs`); the
  provider error `access_denied` reads `consent_declined`; connect scopes come from the policy, never `GOOGLE_DEFAULT`.
- Hardening: Origin rule for cookie-authenticated mutations (`origin_rule.py`); daily `signin_prune` job; real mode has no
  localhost defaults (allowlist required, CORS origins checked against it); startup refuses a database behind head, a
  `fake*` provider outside fake mode, and fake mode on https (`SDK_EXAMPLE_ALLOW_FAKE_PUBLIC=1` to allow); phone connect
  needs an account bound by sign-in; `demo@example.com` is the seeded break-glass row (`allow_password`).
- Fake consent page is an identity picker with scope-set boxes (`sdk-consent-*` ids). New settings
  `SDK_EXAMPLE_SIGNIN_PROVIDERS`, `_PUBLIC_BASE` (also the connect callback base), `_NATIVE_RETURN_BASE`,
  `_NATIVE_SCHEMES`, `_BREAKGLASS`, `BOND_APPLE_APP_IDS`, `BOND_ANDROID_APPS`.
