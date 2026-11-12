#!/usr/bin/env bash
# Boundary gate. Keeps the module layers apart:
#  (i)   a core package (packages/bond_* whose pubspec has no `flutter:` under
#        dependencies) must not import package:flutter, package:universal_io, dart:ui or
#        dart:io in lib/ (a directive split over several lines counts).
#  (ii)  libs/bond_* must not import another libs/* package inside libs/<x>/<x>/
#        (indented and lazy imports, `import os, bond_x`, __import__ and import_module count).
#  (iv)  no libs/bond_*/pyproject.toml lists a bond_ package as a dependency.
#  (iii) no packages/*/pubspec.yaml names intl, flutter_localizations,
#        flutter_riverpod or go_router (demos may).
#  (v)   only packages/bond_push_apple may depend on the `push` plugin, and only
#        packages/bond_auth_secure_storage on `flutter_secure_storage` (demos may).
#
# Usage: bash tool/boundary_gate.sh [--help]
# Exit: 0 clean, 1 violation, 2 nothing scanned.

set -euo pipefail

cd "$(dirname "$0")/.."

case "${1:-}" in
  --help|-h)
    sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'
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
PKGS_GLOB="${BOUNDARY_PKGS_GLOB:-packages/bond_*}"   # BOUNDARY_*_GLOB: aim the gate at a scratch copy in a test
LIBS_GLOB="${BOUNDARY_LIBS_GLOB:-libs/bond_*}"
for p in $PKGS_GLOB; do
  [[ -f "$p/pubspec.yaml" ]] || continue
  if is_flutter_pkg "$p"; then
    flutter_pkgs=$((flutter_pkgs + 1))
    continue
  fi
  core=$((core + 1))
  [[ -d "$p/lib" ]] || continue
  # perl -0 reads the whole file so a directive split over lines (`import\n 'dart:io';`) is still one match
  while IFS= read -r f; do
    perl -0777 -ne 'while (/^[ \t]*(?:import|export)\s+([\x27"](?:package:flutter[\/_a-z]*|package:universal_io[\/_a-z]*|dart:ui|dart:io))/mg) {
      $n = (substr($_, 0, $-[0]) =~ tr/\n//) + 1; $m = $1; $m =~ s/\s+/ /g;
      print "$ARGV:$n: core package imports Flutter, universal_io, dart:io or dart:ui: $m\n" }' "$f" >> "$hits" || true
  done < <(find "$p/lib" -name '*.dart' 2>/dev/null)
done

libs=0
for l in $LIBS_GLOB; do
  [[ -d "$l/$(basename "$l")" ]] || continue
  libs=$((libs + 1))
  me="$(basename "$l")"
  while IFS= read -r other; do
    on="$(basename "$other")"
    [[ "$on" == "$me" ]] && continue
    # a line-start import, `import os, bond_x`, __import__("bond_x") and importlib.import_module("bond_x")
    grep -rnE "^[[:space:]]*(from|import)[[:space:]]+${on}([[:space:]]|\.|,|$)|^[[:space:]]*import[[:space:]].*,[[:space:]]*${on}([[:space:]]|\.|,|$)|(__import__|import_module)[[:space:]]*\([[:space:]]*['\"]${on}[.'\"]" "$l/$me" --include='*.py' 2>/dev/null \
      | sed -E "s/^([^:]+:[0-9]+):(.*)$/\1: lib imports sibling lib ${on}: \2/" >> "$hits" || true
  done < <(ls -d $LIBS_GLOB 2>/dev/null)
done

# (iv) a lib's pyproject must not name a bond_ package (a quoted requirement or a bare `bond_x =` source line);
# its own `name` and the `include` of its package finder are fine. BOUNDARY_LIBS_GLOB lets a test aim it at a copy.
for f in ${LIBS_GLOB}/pyproject.toml; do
  [[ -f "$f" ]] || continue
  grep -nE "\"bond_[A-Za-z0-9_-]+|^[[:space:]]*bond_[A-Za-z0-9_-]+[[:space:]]*=" "$f" 2>/dev/null \
    | grep -vE '^[0-9]+:[[:space:]]*(name|include)[[:space:]]*=' \
    | sed -E "s|^([0-9]+):(.*)\$|${f}:\1: lib pyproject depends on a bond_ package:\2|" >> "$hits" || true
done

pubspecs=0
for f in packages/*/pubspec.yaml; do
  [[ -f "$f" ]] || continue
  pubspecs=$((pubspecs + 1))
  grep -nE '^[[:space:]]+(intl|flutter_localizations|flutter_riverpod|go_router):' "$f" 2>/dev/null \
    | sed -E "s|^([0-9]+):(.*)\$|${f}:\1: forbidden dependency in a shared package:\2|" >> "$hits" || true
  # (v) plugin dependencies stay in the one package that owns them
  dir="$(basename "$(dirname "$f")")"
  if [[ "$dir" != "bond_push_apple" ]]; then
    grep -nE '^[[:space:]]+push:' "$f" 2>/dev/null \
      | sed -E "s|^([0-9]+):(.*)\$|${f}:\1: only bond_push_apple may depend on the push plugin:\2|" >> "$hits" || true
  fi
  if [[ "$dir" != "bond_auth_secure_storage" ]]; then
    grep -nE '^[[:space:]]+flutter_secure_storage:' "$f" 2>/dev/null \
      | sed -E "s|^([0-9]+):(.*)\$|${f}:\1: only bond_auth_secure_storage may depend on flutter_secure_storage:\2|" >> "$hits" || true
  fi
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
