# Vendored and shipped web assets

Shipped as package data; the app serves them by name (`bond_esign.webform.asset_path`). No asset loads anything
from a remote host at run time.

| File | Origin |
| --- | --- |
| `bond-esign.js`, `bond-esign.css` | ours (MIT, like the rest of the repository) |
| `signature_pad.umd.min.js` | vendored, unchanged |
| `LICENSE-signature_pad` | the package's own licence file |

## Decline

`render_panel(view, ..., decline_url="/your/decline/route")` adds, after the sign form (a sibling, never nested), a
`<details class="bond-esign__decline">` "Decline to sign" with its own `<form method="post">` to that URL. The
disclosure is the confirmation step: no script, no dialog. The form posts one field,
`bond_esign_decline_reason` (optional, at most 2000 characters). The app's route reads it with
`bond_esign.webform.parse_decline(form)` (trimmed, control characters removed, `None` when empty) and calls
`decline(...)`. A declined signer's page shows `PanelLabels.declined_message`. The decline block sits outside
`.bond-esign`, so it carries its own copy of the theme custom properties (`--bond-esign-accent` and the rest):
override them on `.bond-esign, .bond-esign__decline` together. Without `decline_url` the open panel is unchanged, but a declined signer's closed panel now always shows `declined_message`.

## signature_pad

- Package: `signature_pad` by Szymon Nowak (szimek)
- Version: 5.1.8
- Source: https://registry.npmjs.org/signature_pad/-/signature_pad-5.1.8.tgz
- Tarball shasum (sha1, as npm lists it): `b15ea159799444b1aa22d59f36424b4cd115e85f`
- sha256 of `signature_pad.umd.min.js`: `67aa4d227733d0a241bd277d49b06ad3d28239c9b8f7c87b2817e439a567de74`
- Licence: MIT (the file keeps its own licence header)

The file ends with a `sourceMappingURL` comment for a map file that is not shipped; it is harmless.

## How to update

1. Download the new tarball from the registry URL above and check its shasum against the registry's `dist.shasum`.
2. Extract it in a fresh empty directory; copy `package/dist/signature_pad.umd.min.js` and `package/LICENSE`
   (as `LICENSE-signature_pad`) over the files here, unchanged.
3. Update this file (version, shasums) and the entry in the repository `NOTICE`.
4. Run the lib tests (`tests/test_web_assets.py`) and walk the panel in a browser: draw, rotate, clear, submit.
