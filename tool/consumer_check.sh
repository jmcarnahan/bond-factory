#!/usr/bin/env bash
# Consumer check. Proves every Dart package resolves OUTSIDE the workspace, the
# way an app consumes it: copy the package to a temp dir, drop
# `resolution: workspace`, point sibling `path: ../<sib>` deps at absolute
# paths, run pub get, and fail on an error or an `intl` pin.
#
# Usage: bash tool/consumer_check.sh [<package-name>...] [--help]
#   no names: every packages/bond_*.
# Env: FLUTTER (default flutter), DART (default dart).
# Slow (2-5 minutes); not part of `make gates`, run via `make consumer-check`.
# Exit: 0 all OK, 1 a package failed, 2 nothing checked.

set -euo pipefail

cd "$(dirname "$0")/.."
W="$(pwd)"
FLUTTER="${FLUTTER:-flutter}"
DART="${DART:-dart}"

names=()
for a in "$@"; do
  case "$a" in
    --help|-h)
      sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) names+=("$a") ;;
  esac
done

if [[ ${#names[@]} -eq 0 ]]; then
  for p in packages/bond_*; do
    [[ -f "$p/pubspec.yaml" ]] && names+=("$(basename "$p")")
  done
fi
if [[ ${#names[@]} -eq 0 ]]; then
  echo "FAIL: no packages found" >&2
  exit 2
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

ok=0
bad=0
for name in "${names[@]}"; do
  src="$W/packages/$name"
  if [[ ! -f "$src/pubspec.yaml" ]]; then
    echo "FAIL $name: no such package"
    bad=$((bad + 1))
    continue
  fi
  dst="$work/$name"
  mkdir -p "$dst"
  # Copy only what pub needs; skip build output and the workspace lock.
  (cd "$src" && tar --exclude='.dart_tool' --exclude='build' --exclude='pubspec.lock' \
    --exclude='pubspec_overrides.yaml' -cf - .) | (cd "$dst" && tar -xf -)
  sed -E -i.bak -e '/^resolution:[[:space:]]*workspace/d' \
    -e "s|path:[[:space:]]*\.\./([A-Za-z0-9_]+)|path: ${W}/packages/\1|" "$dst/pubspec.yaml"
  rm -f "$dst/pubspec.yaml.bak"

  if grep -qE '^  flutter:' "$dst/pubspec.yaml"; then
    tool=("$FLUTTER" pub get)
  else
    tool=("$DART" pub get)
  fi

  log="$work/$name.log"
  if ! (cd "$dst" && "${tool[@]}" > "$log" 2>&1); then
    echo "FAIL $name: pub get failed"
    sed -n '1,15p' "$log"
    bad=$((bad + 1))
    continue
  fi
  if grep -qE '^[[:space:]]+intl:' "$dst/pubspec.yaml"; then
    echo "FAIL $name: pubspec names intl"
    bad=$((bad + 1))
    continue
  fi
  echo "OK $name (${tool[0]##*/} pub get)"
  ok=$((ok + 1))
done

echo "consumer_check: $ok OK, $bad failed"
[[ "$bad" -gt 0 ]] && exit 1
exit 0
