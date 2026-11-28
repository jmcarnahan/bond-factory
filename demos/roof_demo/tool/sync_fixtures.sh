#!/usr/bin/env bash
# Copies every ../../fixtures/*.json and ../../fixtures/roof_engine/*.json whose schema or contract is bond.roof_model/0.x
# (the 0.6 sample, and the older models and envelopes that must still open) into assets/fixtures/. The demo reads these
# files only; no service is called. Run from anywhere (or `make sync-fixtures`). Stale copies are removed first.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
src="$here/../../fixtures"
dst="$here/assets/fixtures"
mkdir -p "$dst"
rm -f "$dst"/*.json
n=0
for f in "$src"/*.json "$src"/roof_engine/*.json; do
  [[ -e "$f" ]] || continue
  if grep -q '"bond.roof_model/0\.' "$f"; then
    cp "$f" "$dst/"
    n=$((n + 1))
  fi
done
# Keep the asset folder non-empty so the pubspec asset entry always resolves.
touch "$dst/.gitkeep"
echo "synced $n fixture(s) into $dst"
