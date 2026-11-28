# Changelog

## 0.1.0 - unreleased
- Test-only host of an app that already exists: renamed columns, app columns, a legacy REST wire, tables that
  pre-date the modules. One test file per trait (see README).
- The calendar mirror opts in to `transport_pending`: no answer from the provider leaves the task `pending`.
- `push_devices` is mounted on the sync upload (the device writes its own row); no REST route.
- Replays what the legacy phone store (`demos/legacy_phone`) queues: an eighth trait.
- Ninth trait, an existing provider seam: `esign_envelopes` + `EsignProvider` pre-date bond_esign; `NativeProvider` adopts it beside a vendor stand-in (adapter under 150 lines), with the host's signing page.
- Ninth trait now calls the seam as an existing app does: `signed` reads "completed", `complete_envelope` and `take_back` (`ALREADY_SIGNED`), label and validity date from the estimate (legacy columns `customer_line`, `valid_until`), the sign POST queues the completion job and redirects with `event=signing_complete`.
