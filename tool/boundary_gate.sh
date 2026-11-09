#!/usr/bin/env bash
# Boundary gate. Keeps the module layers apart:
#  (i)   a core package (packages/bond_* whose pubspec has no `flutter:` under
#        dependencies) must not import package:flutter, dart:ui or dart:io in lib/.
#  (ii)  libs/bond_* must not import another libs/* package inside libs/<x>/<x>/.
#  (iii) no packages/*/pubspec.yaml names intl, flutter_localizations,
#        flutter_riverpod or go_router (demos may).
#
# Usage: bash tool/boundary_gate.sh [--help]
# Exit: 0 clean, 1 violation, 2 nothing scanned.

set -euo pipefail

cd "$(dirname "$0")/.."

case "${1:-}" in
  --help|-h)
    sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
    ;;
  "") ;;
  *) echo "unknown argument: $1 (try --help)" >&2; exit 2 ;;
esac

hits="$(mktemp)"
trap 'rm -f "$hits"' EXIT

# True when the pubspec declares `flutter:` with an sdk under dependencies.
is_flutter_pkg() {
  awk '
    /^dependencies:/ { dep=1; next }
    /^[a-z_]+:/ { dep=0 }
    dep && /^  flutter:/ { found=1 }
    END { exit found ? 0 : 1 }
  ' "$1/pubspec.yaml"
}

core=0
flutter_pkgs=0
for p in packages/bond_*; do
  [[ -f "$p/pubspec.yaml" ]] || continue
  if is_flutter_pkg "$p"; then
    flutter_pkgs=$((flutter_pkgs + 1))
    continue
  fi
  core=$((core + 1))
  [[ -d "$p/lib" ]] || continue
  grep -rnE "^[[:space:]]*(import|export)[[:space:]]+['\"](package:flutter[/_a-z]*|dart:ui|dart:io)" \
    "$p/lib" --include='*.dart' 2>/dev/null \
    | sed -E 's/^([^:]+:[0-9]+):(.*)$/\1: core package imports Flutter or dart:io|dart:ui: \2/' >> "$hits" || true
done

libs=0
for l in libs/bond_*; do
  [[ -d "$l/$(basename "$l")" ]] || continue
  libs=$((libs + 1))
  me="$(basename "$l")"
  while IFS= read -r other; do
    on="$(basename "$other")"
    [[ "$on" == "$me" ]] && continue
    grep -rnE "^(from|import)[[:space:]]+${on}([[:space:]]|\.|$)" "$l/$me" --include='*.py' 2>/dev/null \
      | sed -E "s/^([^:]+:[0-9]+):(.*)$/\1: lib imports sibling lib ${on}: \2/" >> "$hits" || true
  done < <(ls -d libs/bond_* 2>/dev/null)
done

pubspecs=0
for f in packages/*/pubspec.yaml; do
  [[ -f "$f" ]] || continue
  pubspecs=$((pubspecs + 1))
  grep -nE '^[[:space:]]+(intl|flutter_localizations|flutter_riverpod|go_router):' "$f" 2>/dev/null \
    | sed -E "s|^([0-9]+):(.*)\$|${f}:\1: forbidden dependency in a shared package:\2|" >> "$hits" || true
done

if [[ $((core + libs + pubspecs)) -eq 0 ]]; then
  echo "FAIL: nothing scanned" >&2
  exit 2
fi

count="$(grep -c . "$hits" || true)"
[[ "$count" -gt 0 ]] && cat "$hits"
echo "boundary_gate: scanned $core core packages ($flutter_pkgs flutter skipped), $libs python libs, $pubspecs pubspecs, $count violation(s)"
[[ "$count" -gt 0 ]] && exit 1
exit 0
