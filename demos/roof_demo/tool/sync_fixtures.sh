#!/usr/bin/env bash
# Copies every ../../fixtures/*.json whose schema is bond.roof_model/0.1 into
# assets/fixtures/ so the demo works with no service running. Run from anywhere
# (or `make sync-fixtures` at the repo root). Stale copies are removed first.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
src="$here/../../fixtures"
dst="$here/assets/fixtures"
mkdir -p "$dst"
rm -f "$dst"/*.json
n=0
for f in "$src"/*.json; do
  [[ -e "$f" ]] || continue
  if grep -q '"bond.roof_model/0.1"' "$f"; then
    cp "$f" "$dst/"
    n=$((n + 1))
  fi
done
# Keep the asset folder non-empty so the pubspec asset entry always resolves.
touch "$dst/.gitkeep"
echo "synced $n fixture(s) into $dst"
