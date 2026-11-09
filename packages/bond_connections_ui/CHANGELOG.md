# Changelog

## 0.1.0 - unreleased
- `BondConnectionCard`: state chip, e-mail, formatted date, buttons by state, inline two-step disconnect.
- `BondConnectionsList` and `BondConnectionReturnBanner`.
- `semanticsId` is a prefix: `<prefix>.card-<provider>`, `.state-<provider>`, `.connect-`, `.reconnect-`, `.disconnect-`.
- The state chip is one semantics node `<prefix>.state-<provider>` whose label is the chip text.
- The return banner is drawn by this package (not `BondBanner`): one live-region node `<id>` labelled with the title
  and message, and the dismiss button as its own node `<id>-dismiss`. The text is exposed once.
