#!/usr/bin/env bash
# Prints the modules affected by changes vs $BASE (default main), including
# uncommitted and untracked paths. With --test, runs `make -C <module> test` for each.
set -euo pipefail
cd "$(dirname "$0")/.."

BASE="${BASE:-main}"
ALL="packages/bond_roof packages/bond_roof_ui demos/roof_demo services/roof_measure"

# prefix -> affected modules (reverse dependencies)
affected() {
  case "$1" in
    packages/bond_roof/*)    echo packages/bond_roof packages/bond_roof_ui demos/roof_demo ;;
    packages/bond_roof_ui/*) echo packages/bond_roof_ui demos/roof_demo ;;
    demos/roof_demo/*)       echo demos/roof_demo ;;
    services/roof_measure/*) echo services/roof_measure ;;
    fixtures/*)              echo packages/bond_roof services/roof_measure demos/roof_demo ;;
    docs/contracts/*)        echo packages/bond_roof services/roof_measure ;;
    pyproject.toml|uv.lock)  echo services/roof_measure ;;
    pubspec.yaml|pubspec.lock|analysis_options.yaml|Makefile|make/*|tool/*) echo "$ALL" ;;
  esac
}

paths="$( { git diff --name-only "$BASE" 2>/dev/null || true
            git status --porcelain | sed -E 's/^.{3}//; s/.* -> //'; } | sort -u )"

mods=""
while IFS= read -r p; do
  [[ -z "$p" ]] && continue
  mods="$mods $(affected "$p")"
done <<< "$paths"

list="$(printf '%s\n' $mods | sort -u | grep . || true)"
if [[ -z "$list" ]]; then echo "no modules affected"; exit 0; fi
echo "$list"

if [[ "${1:-}" == "--test" ]]; then
  for m in $list; do
    if [[ ! -f "$m/Makefile" ]]; then echo "== $m: no Makefile, skipped"; continue; fi
    echo "== $m"
    make -C "$m" test
  done
fi
