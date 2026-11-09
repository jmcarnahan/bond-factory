#!/usr/bin/env bash
# Public-hygiene gate. This repo is public. Scans tracked files under
#   packages libs services demos fixtures tool make .github docs/sdk docs/decisions docs/contracts docs/test
#   and the root files pubspec.yaml pyproject.toml Makefile (README.md and CLAUDE.md name the apps on purpose)
# for e-mail addresses, API keys, private keys, cloud access keys, Firebase
# hosting names and the brand denylist, and fails on fixtures over 100 KB.
# Exempt: this script, docs/migration/**, local/**, and paths listed in
# tool/allowlist_hygiene.txt.
# Allowed e-mails: noreply@anthropic.com, *@example.com, *@example.org.
#
# Usage: bash tool/public_hygiene.sh [--worktree] [--help]
#   --worktree  also scan untracked, non-ignored files (default: tracked only)
# Exit: 0 clean, 1 violation, 2 nothing scanned.

set -euo pipefail

cd "$(dirname "$0")/.."

WORKTREE=0
case "${1:-}" in
  --help|-h)
    sed -n "2,13p" "$0" | sed 's/^# \{0,1\}//'
    exit 0
    ;;
  --worktree) WORKTREE=1 ;;
  "") ;;
  *) echo "unknown argument: $1 (try --help)" >&2; exit 2 ;;
esac

ROOTS=(packages libs services demos fixtures tool make .github docs/sdk docs/decisions docs/contracts docs/test
       pubspec.yaml pyproject.toml Makefile)

list="$(mktemp)"
hits="$(mktemp)"
trap 'rm -f "$list" "$hits"' EXIT

if [[ "$WORKTREE" -eq 1 ]]; then
  git ls-files -co --exclude-standard -- "${ROOTS[@]}" > "$list"
else
  git ls-files -- "${ROOTS[@]}" > "$list"
fi

# Drop exemptions and files that no longer exist (deleted but still indexed).
filtered="$(mktemp)"
trap 'rm -f "$list" "$hits" "$filtered"' EXIT
allow="$(mktemp)"
trap 'rm -f "$list" "$hits" "$filtered" "$allow"' EXIT
if [[ -f tool/allowlist_hygiene.txt ]]; then
  sed -E 's/#.*$//; s/^[[:space:]]+|[[:space:]]+$//g' tool/allowlist_hygiene.txt | grep . > "$allow" || true
fi
while IFS= read -r f; do
  case "$f" in
    tool/public_hygiene.sh|docs/migration/*|local/*) continue ;;
  esac
  grep -qxF "$f" "$allow" && continue
  [[ -f "$f" ]] && echo "$f"
done < "$list" | sort -u > "$filtered"

scanned="$(grep -c . "$filtered" || true)"
if [[ "$scanned" -eq 0 ]]; then
  echo "FAIL: no tracked files to scan" >&2
  exit 2
fi

# scan <label> <grep -E pattern> [extra grep flags...]
scan() {
  local label="$1" pat="$2"
  shift 2
  tr '\n' '\0' < "$filtered" \
    | xargs -0 grep -InE "$@" -e "$pat" 2>/dev/null \
    | sed -E "s/^([^:]+:[0-9]+):(.*)\$/\1: ${label}: \2/" >> "$hits" || true
}

# E-mail addresses, minus the allowed ones.
mail_tmp="$(mktemp)"
trap 'rm -f "$list" "$hits" "$filtered" "$mail_tmp"' EXIT
tr '\n' '\0' < "$filtered" \
  | xargs -0 grep -InE '[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}' 2>/dev/null \
  > "$mail_tmp" || true
while IFS= read -r line; do
  # keep the line only if it holds an address that is not on the allow list
  addrs="$(printf '%s\n' "$line" | grep -oE '[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}' || true)"
  bad=0
  while IFS= read -r a; do
    [[ -z "$a" ]] && continue
    case "$a" in
      noreply@anthropic.com|*@example.com|*@example.org) ;;
      *@[0-9]x.png|*@[0-9]x.jpg|*@[0-9]x.webp) ;;  # asset names such as Icon@2x.png
      *) bad=1 ;;
    esac
  done <<< "$addrs"
  [[ "$bad" -eq 1 ]] && printf '%s\n' "$line" | sed -E 's/^([^:]+:[0-9]+):(.*)$/\1: e-mail address: \2/' >> "$hits"
done < "$mail_tmp"

scan "Google API key" 'AIza[0-9A-Za-z_-]{35}'
scan "private key" '-----BEGIN [A-Z ]*PRIVATE KEY'
scan "AWS access key" 'AKIA[0-9A-Z]{16}'

# Firebase hosting names, except placeholders.
fb_tmp="$(mktemp)"
trap 'rm -f "$list" "$hits" "$filtered" "$mail_tmp" "$fb_tmp"' EXIT
tr '\n' '\0' < "$filtered" \
  | xargs -0 grep -InE '[a-z0-9-]+\.firebaseapp\.com' 2>/dev/null > "$fb_tmp" || true
while IFS= read -r line; do
  names="$(printf '%s\n' "$line" | grep -oE '[<a-z0-9-]+\.firebaseapp\.com' || true)"
  bad=0
  while IFS= read -r n; do
    [[ -z "$n" ]] && continue
    case "$n" in
      *example*|\<*|project.firebaseapp.com) ;;
      *) bad=1 ;;
    esac
  done <<< "$names"
  [[ "$bad" -eq 1 ]] && printf '%s\n' "$line" | sed -E 's/^([^:]+:[0-9]+):(.*)$/\1: Firebase project name: \2/' >> "$hits"
done < "$fb_tmp"

# Brand denylist: words (case-insensitive, start of word) and app identifiers.
scan "brand name" '(avalon|sbel|pagatime|bondable)' -i
scan "brand name" '(^|[^A-Za-z])paga' -i
scan "Google OAuth client id" '[0-9]+-[a-z0-9]+\.apps\.googleusercontent\.com'
scan "Firebase app id" '1:[0-9]+:(web|ios|android):[0-9a-f]+'
scan "brand identifier" '(^|[^A-Za-z0-9_])(Av[A-Z][A-Za-z]+|Pt[A-Z][A-Za-z]+|Sbel[A-Z])'

# Fixtures larger than 100 KB.
big=0
while IFS= read -r f; do
  case "$f" in
    fixtures/*)
      size="$(wc -c < "$f" | tr -d ' ')"
      if [[ "$size" -gt 102400 ]]; then
        echo "$f:1: fixture is $size bytes, over the 100 KB limit" >> "$hits"
        big=$((big + 1))
      fi
      ;;
  esac
done < "$filtered"

count="$(grep -c . "$hits" || true)"
[[ "$count" -gt 0 ]] && sort -u "$hits"
echo "public_hygiene: scanned $scanned files, $count violation(s)"
[[ "$count" -gt 0 ]] && exit 1
exit 0
