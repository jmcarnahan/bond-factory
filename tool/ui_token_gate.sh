#!/usr/bin/env bash
# UI token gate. Raw colours belong in tokens: scans packages/bond_ui/lib,
# packages/bond_*_ui/lib and demos/*/lib for Colors.x, CupertinoColors.x,
# Color(0x..), Color(<decimal>), Color.fromARGB, Color.fromRGBO, HSLColor and HSVColor.
# Exempt: any lib/src/tokens/ directory (or a single lib/src/tokens.dart) and
# demos/*/lib/src/theme.dart.
#
# Usage: bash tool/ui_token_gate.sh [--warn] [--self-test] [--help]
#   --self-test  plants a raw colour in a temp copy and expects exit 1 (run by hand, not in make gates)
# Exit: 0 clean (or --warn), 1 violation, 2 nothing scanned.

set -euo pipefail

cd "$(dirname "$0")/.."

WARN=0
case "${1:-}" in
  --help|-h)
    sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
    ;;
  --self-test)
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' EXIT
    mkdir -p "$tmp/tool" "$tmp/demos/x/lib/src" "$tmp/packages/bond_ui/lib/src/tokens"
    cp "$0" "$tmp/tool/ui_token_gate.sh"
    printf 'final a = 1;\n' > "$tmp/demos/x/lib/a.dart"
    printf 'const c = Color(0xFF112233);\n' > "$tmp/packages/bond_ui/lib/src/tokens/t.dart"
    if ! bash "$tmp/tool/ui_token_gate.sh" > /dev/null; then echo "self-test FAIL: clean tree rejected"; exit 1; fi
    for bad in 'const c = Color(0xFF112233);' 'const c = Color(  4278190080);' 'final c = Colors.red;' \
               'final c = HSLColor.fromAHSL(1, 0, 0, 0);' 'final c = CupertinoColors.systemRed;'; do
      printf '%s\n' "$bad" > "$tmp/packages/bond_ui/lib/src/bad.dart"
      if bash "$tmp/tool/ui_token_gate.sh" > /dev/null; then echo "self-test FAIL: not caught: $bad"; exit 1; fi
    done
    echo "self-test OK: bond_ui is scanned, tokens/ is exempt, 5 raw-colour forms are caught"
    exit 0
    ;;
  --warn) WARN=1 ;;
  "") ;;
  *) echo "unknown argument: $1 (try --help)" >&2; exit 2 ;;
esac

RE='Colors\.[a-zA-Z]|CupertinoColors\.[a-zA-Z]|Color\(0x|Color\([[:space:]]*[0-9]|Color\.fromARGB|Color\.fromRGBO|HSLColor|HSVColor'

dirs=()
for d in packages/bond_ui/lib packages/bond_*_ui/lib demos/*/lib; do
  [[ -d "$d" ]] && dirs+=("$d")
done
if [[ ${#dirs[@]} -eq 0 ]]; then
  echo "FAIL: no lib dirs found (packages/bond_ui/lib, packages/bond_*_ui/lib, demos/*/lib)" >&2
  exit 2
fi

hits="$(mktemp)"
trap 'rm -f "$hits"' EXIT

scanned=0
while IFS= read -r f; do
  case "$f" in
    */lib/src/tokens/*|*/lib/src/tokens.dart) continue ;;
    demos/*/lib/src/theme.dart) continue ;;
  esac
  scanned=$((scanned + 1))
  # print file:line: text, skipping pure comment lines
  grep -nE "$RE" "$f" 2>/dev/null \
    | awk -v f="$f" -F: '{
        line=$1; rest=$0; sub(/^[^:]*:/, "", rest);
        t=rest; gsub(/^[ \t]+/, "", t);
        if (t !~ /^\/\//) printf "%s:%s: raw colour (use BondTokens): %s\n", f, line, t
      }' >> "$hits" || true
done < <(find "${dirs[@]}" -name '*.dart' -type f | sort)

if [[ "$scanned" -eq 0 ]]; then
  echo "FAIL: no dart files scanned" >&2
  exit 2
fi

count="$(grep -c . "$hits" || true)"
if [[ "$count" -gt 0 ]]; then
  cat "$hits"
fi
echo "ui_token_gate: scanned $scanned files in ${#dirs[@]} lib dirs, $count violation(s)"

if [[ "$count" -gt 0 && "$WARN" -eq 0 ]]; then
  exit 1
fi
exit 0
