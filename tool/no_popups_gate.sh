#!/usr/bin/env bash
# No-popups gate. Scans app and package sources (not tests) for widgets and
# calls that open something over the page. See the root CLAUDE.md, "HARD RULE:
# no popups, ever".
#
# Allowlist: tool/allowlist_popups.txt, one entry per line,
#   path:Symbol  # reason
# A match is allowed when its file is `path` and the matched line contains
# `Symbol`. More than 6 entries fails the gate.
#
# Default mode is warn-only (exit 0). --enforce exits 1 on any violation.
# Only packages/*/lib and demos/*/lib are scanned; tests are not. The gate fails
# with exit 2 when no lib dirs are found, so it can never pass vacuously.

set -euo pipefail

cd "$(dirname "$0")/.."

ENFORCE=0
[[ "${1:-}" == "--enforce" ]] && ENFORCE=1

POPUP_RE='showDialog|showGeneralDialog|showCupertinoDialog|showAdaptiveDialog|showCupertinoModalPopup|showCupertinoSheet|showModalBottomSheet|showBottomSheet|AlertDialog|SimpleDialog|CupertinoAlertDialog|CupertinoActionSheet|CupertinoContextMenu|CupertinoPicker|PopupMenuButton|PopupMenuItem|PopupRoute|RawDialogRoute|DialogRoute|showMenu\(|MenuAnchor|MenuBar|MenuItemButton|SubmenuButton|MenuController|ContextMenuController|showDatePicker|showTimePicker|showDateRangePicker|DatePickerDialog|TimePickerDialog|DropdownButtonFormField|DropdownMenuItem|DropdownMenu|DropdownButton|Autocomplete|RawAutocomplete|SearchAnchor|showSearch|showAboutDialog|showLicensePage|Drawer|endDrawer|BottomSheet|DraggableScrollableSheet|SnackBar|ScaffoldMessenger|MaterialBanner|Tooltip|tooltip:|OverlayEntry|OverlayPortal|Overlay\.of|Overlay\.maybeOf|OverlayState|CupertinoModalPopupRoute|opaque:[[:space:]]*false|CompositedTransformFollower|ModalBarrier\(|Dialog\(|[A-Za-z]+WithPopup'

ALLOWLIST=tool/allowlist_popups.txt

entries=()
if [[ -f "$ALLOWLIST" ]]; then
  while IFS= read -r raw; do
    line="${raw%%#*}"
    line="$(echo "$line" | sed -E 's/^[[:space:]]+|[[:space:]]+$//g')"
    [[ -z "$line" ]] && continue
    entries+=("$line")
  done < "$ALLOWLIST"
fi

dirs=()
for d in packages/*/lib demos/*/lib; do
  [[ -d "$d" ]] && dirs+=("$d")
done
if [[ ${#dirs[@]} -eq 0 ]]; then
  echo "FAIL: no lib dirs found (looked in packages/*/lib demos/*/lib)" >&2
  exit 2
fi

violations_file="$(mktemp)"
trap 'rm -f "$violations_file"' EXIT

if [[ ${#dirs[@]} -gt 0 ]]; then
  grep -rnE "$POPUP_RE" "${dirs[@]}" --include='*.dart' 2>/dev/null \
    | grep -v '/lib/l10n/gen/' \
    | awk -F: '{ rest=$0; sub(/^[^:]*:[^:]*:/, "", rest); gsub(/^[ \t]+/, "", rest); if (rest !~ /^\/\//) print $0 }' \
    > "$violations_file" || true
fi

# Drop matches the allowlist covers. A line is allowed only when EVERY banned
# token on it is allowlisted for that file as an exact symbol, so allowing
# DropdownButton never allows DropdownButtonFormField.
remaining="$(mktemp)"
trap 'rm -f "$violations_file" "$remaining"' EXIT
while IFS= read -r hit; do
  [[ -z "$hit" ]] && continue
  file="${hit%%:*}"
  content="${hit#*:*:}"
  all_ok=1
  while IFS= read -r token; do
    [[ -z "$token" ]] && continue
    tok_ok=0
    for e in "${entries[@]+"${entries[@]}"}"; do
      epath="${e%%:*}"
      esym="${e#*:}"
      esym="$(echo "$esym" | sed -E 's/^[[:space:]]+|[[:space:]]+$//g')"
      if [[ "$file" == "$epath" && "$token" == "$esym" ]]; then
        tok_ok=1
        break
      fi
    done
    [[ "$tok_ok" -eq 0 ]] && all_ok=0
  done < <(printf '%s\n' "$content" | grep -oE "$POPUP_RE")
  [[ "$all_ok" -eq 0 ]] && echo "$hit" >> "$remaining"
done < "$violations_file"

count="$(grep -c . "$remaining" || true)"
n_entries=${#entries[@]}

echo "-- No-popups gate ------------------------------------------"
echo "allowlist entries: $n_entries (max 6)"
echo "lib dirs scanned: ${#dirs[@]}"

fail=0
if [[ "$n_entries" -gt 6 ]]; then
  echo "FAIL: allowlist has more than 6 entries"
  fail=1
fi

if [[ "$count" -eq 0 ]]; then
  echo "clean: no popup widgets or calls outside the allowlist"
else
  echo "$count violation(s):"
  sed -n '1,200p' "$remaining"
  fail=1
fi

if [[ "$fail" -eq 1 && "$ENFORCE" -eq 1 ]]; then
  echo
  echo "FAIL (--enforce): the app does not use popups. Render it inline."
  exit 1
fi
if [[ "$fail" -eq 1 ]]; then
  echo
  echo "warn-only mode: exiting 0. Run with --enforce to fail."
fi
exit 0
