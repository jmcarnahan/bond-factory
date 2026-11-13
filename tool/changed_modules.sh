#!/usr/bin/env bash
# Prints the modules affected by changes vs $BASE (default main), including
# uncommitted and untracked paths. With --test, runs `make -C <module> test` for each.
set -euo pipefail
cd "$(dirname "$0")/.."

BASE="${BASE:-main}"
if ! git rev-parse --verify --quiet "$BASE^{commit}" >/dev/null; then
  echo "changed_modules: base ref '$BASE' cannot be resolved (shallow clone? run: git fetch origin $BASE:$BASE, or set BASE=<ref>)" >&2
  exit 2
fi
ALL="packages/bond_roof packages/bond_roof_ui demos/roof_demo services/roof_measure packages/bond_json packages/bond_api packages/bond_test_support packages/bond_ui packages/bond_auth packages/bond_auth_firebase packages/bond_sync packages/bond_sync_powersync packages/bond_tasks packages/bond_tasks_ui packages/bond_connections packages/bond_connections_ui packages/bond_signin packages/bond_signin_ui demos/sdk_demo libs/bond_service_kit libs/bond_storage libs/bond_auth_py libs/bond_jobs libs/bond_sync_py libs/bond_oauth libs/bond_calendar libs/bond_tasks_py libs/bond_signin services/sdk_example packages/bond_notify packages/bond_notify_ui packages/bond_push packages/bond_push_apple packages/bond_auth_secure_storage packages/bond_tasks_notifications packages/bond_tasks_powersync packages/bond_notify_powersync libs/bond_notify_py libs/bond_push_py libs/bond_capture_py services/legacy_host demos/legacy_phone"

# prefix -> affected modules (reverse dependencies)
affected() {
  case "$1" in
    packages/bond_roof/*)    echo packages/bond_roof packages/bond_roof_ui demos/roof_demo ;;
    packages/bond_roof_ui/*) echo packages/bond_roof_ui demos/roof_demo ;;
    demos/roof_demo/*)       echo demos/roof_demo ;;
    services/roof_measure/*) echo services/roof_measure ;;
    packages/bond_json/*)  echo packages/bond_json packages/bond_api packages/bond_auth packages/bond_sync packages/bond_tasks packages/bond_connections packages/bond_auth_firebase packages/bond_sync_powersync packages/bond_tasks_ui packages/bond_connections_ui packages/bond_signin packages/bond_signin_ui demos/sdk_demo packages/bond_notify packages/bond_notify_ui packages/bond_push packages/bond_push_apple packages/bond_tasks_notifications packages/bond_tasks_powersync packages/bond_notify_powersync packages/bond_auth_secure_storage demos/legacy_phone ;;
    packages/bond_api/*)   echo packages/bond_api packages/bond_auth packages/bond_sync packages/bond_tasks packages/bond_connections packages/bond_auth_firebase packages/bond_sync_powersync packages/bond_tasks_ui packages/bond_connections_ui packages/bond_signin packages/bond_signin_ui demos/sdk_demo packages/bond_notify packages/bond_notify_ui packages/bond_push packages/bond_push_apple packages/bond_tasks_notifications packages/bond_tasks_powersync packages/bond_notify_powersync packages/bond_auth_secure_storage demos/legacy_phone ;;
    packages/bond_test_support/*)  echo packages/bond_test_support packages/bond_ui packages/bond_tasks_ui packages/bond_connections_ui packages/bond_signin_ui demos/sdk_demo packages/bond_notify_ui packages/bond_push packages/bond_tasks_notifications packages/bond_tasks_powersync packages/bond_notify_powersync demos/legacy_phone ;;
    packages/bond_ui/*)    echo packages/bond_ui packages/bond_tasks_ui packages/bond_connections_ui packages/bond_signin_ui demos/sdk_demo packages/bond_notify_ui demos/legacy_phone ;;
    packages/bond_auth/*)  echo packages/bond_auth packages/bond_auth_secure_storage packages/bond_auth_firebase packages/bond_signin packages/bond_signin_ui demos/sdk_demo ;;
    packages/bond_auth_firebase/*)  echo packages/bond_auth_firebase demos/sdk_demo ;;
    packages/bond_sync/*)  echo packages/bond_sync packages/bond_sync_powersync demos/sdk_demo packages/bond_tasks_powersync packages/bond_notify_powersync demos/legacy_phone ;;
    packages/bond_sync_powersync/*)  echo packages/bond_sync_powersync demos/sdk_demo packages/bond_tasks_powersync packages/bond_notify_powersync demos/legacy_phone ;;
    packages/bond_tasks/*)  echo packages/bond_tasks packages/bond_tasks_ui demos/sdk_demo packages/bond_tasks_notifications packages/bond_tasks_powersync demos/legacy_phone ;;
    packages/bond_tasks_ui/*)  echo packages/bond_tasks_ui demos/sdk_demo demos/legacy_phone ;;
    packages/bond_connections/*)  echo packages/bond_connections packages/bond_connections_ui packages/bond_signin packages/bond_signin_ui demos/sdk_demo ;;
    packages/bond_connections_ui/*)  echo packages/bond_connections_ui demos/sdk_demo ;;
    packages/bond_signin/*)  echo packages/bond_signin packages/bond_signin_ui demos/sdk_demo ;;
    packages/bond_signin_ui/*)  echo packages/bond_signin_ui demos/sdk_demo ;;
    packages/bond_notify/*)  echo packages/bond_notify packages/bond_notify_ui packages/bond_tasks_notifications packages/bond_notify_powersync demos/sdk_demo demos/legacy_phone ;;
    packages/bond_notify_ui/*)  echo packages/bond_notify_ui demos/sdk_demo ;;
    packages/bond_push/*)  echo packages/bond_push packages/bond_push_apple packages/bond_tasks_notifications packages/bond_notify_powersync demos/sdk_demo demos/legacy_phone ;;
    packages/bond_push_apple/*)  echo packages/bond_push_apple demos/sdk_demo ;;
    packages/bond_auth_secure_storage/*)  echo packages/bond_auth_secure_storage ;;
    packages/bond_tasks_notifications/*)  echo packages/bond_tasks_notifications demos/sdk_demo demos/legacy_phone ;;
    packages/bond_tasks_powersync/*)  echo packages/bond_tasks_powersync demos/sdk_demo demos/legacy_phone ;;
    packages/bond_notify_powersync/*)  echo packages/bond_notify_powersync demos/sdk_demo ;;
    demos/sdk_demo/*)        echo demos/sdk_demo ;;
    libs/bond_service_kit/*) echo libs/bond_service_kit services/sdk_example services/legacy_host ;;
    libs/bond_storage/*) echo libs/bond_storage services/sdk_example services/legacy_host ;;
    libs/bond_auth_py/*) echo libs/bond_auth_py libs/bond_signin services/sdk_example ;;
    libs/bond_jobs/*) echo libs/bond_jobs services/sdk_example ;;
    libs/bond_sync_py/*) echo libs/bond_sync_py services/sdk_example services/legacy_host ;;
    libs/bond_oauth/*) echo libs/bond_oauth services/sdk_example ;;
    libs/bond_calendar/*) echo libs/bond_calendar services/sdk_example services/legacy_host ;;
    libs/bond_tasks_py/*) echo libs/bond_tasks_py services/sdk_example services/legacy_host ;;
    libs/bond_signin/*) echo libs/bond_signin services/sdk_example ;;
    libs/bond_notify_py/*) echo libs/bond_notify_py services/sdk_example services/legacy_host ;;
    libs/bond_push_py/*) echo libs/bond_push_py services/sdk_example services/legacy_host ;;
    libs/bond_capture_py/*) echo libs/bond_capture_py services/sdk_example ;;
    services/sdk_example/*)  echo services/sdk_example ;;
    services/legacy_host/*)  echo services/legacy_host ;;
    demos/legacy_phone/*)  echo demos/legacy_phone ;;
    fixtures/sync/*)         echo packages/bond_sync libs/bond_sync_py services/sdk_example ;;
    fixtures/tasks/*)        echo packages/bond_tasks packages/bond_tasks_ui packages/bond_tasks_notifications packages/bond_tasks_powersync libs/bond_tasks_py services/sdk_example demos/sdk_demo ;;
    fixtures/notify/*)       echo libs/bond_notify_py packages/bond_notify packages/bond_notify_ui packages/bond_notify_powersync services/sdk_example demos/sdk_demo ;;
    fixtures/push/*)         echo libs/bond_push_py packages/bond_push services/sdk_example ;;
    fixtures/capture/*)      echo libs/bond_capture_py packages/bond_tasks services/sdk_example ;;
    fixtures/signin/*)       echo libs/bond_signin packages/bond_signin packages/bond_signin_ui services/sdk_example demos/sdk_demo ;;
    fixtures/legacy_host/*)  echo packages/bond_tasks packages/bond_api services/legacy_host demos/legacy_phone packages/bond_notify_powersync ;;
    fixtures/*)              echo packages/bond_roof services/roof_measure demos/roof_demo ;;
    docs/contracts/*|docs/contract-0.2.md) echo packages/bond_roof services/roof_measure demos/roof_demo ;;
    docs/decisions/2026-11-10-roof-module-v1.md|docs/decisions/2026-11-11-roof-dart-packages-mit.md|docs/research/2026-11-10-roof-module-v1/*) echo packages/bond_roof packages/bond_roof_ui services/roof_measure ;;
    pyproject.toml|uv.lock)  echo services/roof_measure libs/bond_service_kit libs/bond_storage libs/bond_auth_py libs/bond_jobs libs/bond_sync_py libs/bond_oauth libs/bond_calendar libs/bond_tasks_py libs/bond_signin libs/bond_notify_py libs/bond_push_py libs/bond_capture_py services/sdk_example services/legacy_host ;;
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
