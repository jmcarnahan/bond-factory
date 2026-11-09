#!/usr/bin/env bash
# Line-cap gate. Source files only (no tests, no alembic/versions):
#   packages/*/lib/**/*.dart, demos/*/lib/**/*.dart,
#   libs/*/<pkg>/**/*.py, services/*/<pkg>/**/*.py
# Warns above 300 lines, fails above 450. Allowlist: tool/allowlist_linecap.txt.
#
# Usage: bash tool/line_cap_gate.sh [--warn] [--help]
# Exit: 0 clean (or --warn), 1 a file exceeds 450, 2 nothing scanned.

set -euo pipefail

cd "$(dirname "$0")/.."

SOFT=300
HARD=450
WARN=0
case "${1:-}" in
  --help|-h)
    sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
    ;;
  --warn) WARN=1 ;;
  "") ;;
  *) echo "unknown argument: $1 (try --help)" >&2; exit 2 ;;
esac

allow="$(mktemp)"
files="$(mktemp)"
trap 'rm -f "$allow" "$files"' EXIT

if [[ -f tool/allowlist_linecap.txt ]]; then
  sed -E 's/#.*$//; s/^[[:space:]]+|[[:space:]]+$//g' tool/allowlist_linecap.txt | grep . > "$allow" || true
fi

# Dart sources.
for d in packages/*/lib demos/*/lib; do
  [[ -d "$d" ]] && find "$d" -name '*.dart' -type f >> "$files"
done
# Python sources: <module>/<pkg>/**/*.py where <pkg> is the module's package dir.
for m in libs/* services/*; do
  [[ -d "$m" ]] || continue
  pkg="$m/$(basename "$m")"
  [[ -d "$pkg" ]] && find "$pkg" -name '*.py' -type f -not -path '*/alembic/versions/*' >> "$files"
done
# alembic/ at a service root is outside <pkg>/, so it is not scanned.

scanned=0
warned=0
failed=0
while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  scanned=$((scanned + 1))
  n="$(wc -l < "$f" | tr -d ' ')"
  [[ "$n" -le "$SOFT" ]] && continue
  if grep -qxF "$f" "$allow"; then
    echo "$f:1: $n lines (allowlisted)"
    continue
  fi
  if [[ "$n" -gt "$HARD" ]]; then
    echo "$f:1: $n lines, over the $HARD hard cap (split it)"
    failed=$((failed + 1))
  else
    echo "$f:1: $n lines, over the $SOFT soft cap (warning)"
    warned=$((warned + 1))
  fi
done < <(sort "$files")

if [[ "$scanned" -eq 0 ]]; then
  echo "FAIL: no source files scanned" >&2
  exit 2
fi

echo "line_cap_gate: scanned $scanned files, $warned over $SOFT (warn), $failed over $HARD (fail)"
if [[ "$failed" -gt 0 && "$WARN" -eq 0 ]]; then
  exit 1
fi
exit 0
