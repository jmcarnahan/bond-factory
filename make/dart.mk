# Dart and Flutter targets. DART_PKGS are pure Dart; FLUTTER_PKGS need the Flutter SDK.
DART_PKGS = packages/bond_roof packages/bond_json packages/bond_api packages/bond_auth packages/bond_sync packages/bond_tasks packages/bond_notify packages/bond_connections packages/bond_signin
FLUTTER_PKGS = packages/bond_notify_ui packages/bond_push packages/bond_push_apple packages/bond_auth_secure_storage packages/bond_tasks_notifications packages/bond_tasks_powersync packages/bond_notify_powersync packages/bond_roof_ui demos/roof_demo packages/bond_test_support packages/bond_ui packages/bond_auth_firebase packages/bond_sync_powersync packages/bond_tasks_ui packages/bond_connections_ui packages/bond_signin_ui demos/sdk_demo demos/legacy_phone

# Tests run in one fixed non-UTC zone: the stage and day-view fixtures are asserted for America/Los_Angeles,
# and a UTC machine would hide naive-timestamp bugs. Override with TEST_TZ=<zone>.
TEST_TZ ?= America/Los_Angeles

.PHONY: test-sync-service sync-fixtures demo-web demo-ios build-web demo-sdk-web test-dart test-flutter analyze

demo-sdk-web: ## Serve the SDK demo on :8078 (debug web-server)
	$(MAKE) -C demos/sdk_demo serve-web


sync-fixtures: ## Copy roof-model fixtures into the demo's assets
	demos/roof_demo/tool/sync_fixtures.sh

demo-web: sync-fixtures ## Run the demo in Chrome
	cd demos/roof_demo && $(FLUTTER) run -d chrome

build-web: sync-fixtures ## Release web build of the demo
	cd demos/roof_demo && $(FLUTTER) build web --release
	@echo "built demos/roof_demo/build/web (serve it with: cd demos/roof_demo/build/web && python3 -m http.server 8077)"

demo-ios: sync-fixtures ## Run the demo on the booted iOS simulator
	cd demos/roof_demo && $(FLUTTER) run -d "$$(xcrun simctl list devices booted -j | python3 -c 'import json,sys; d=json.load(sys.stdin)["devices"]; print(next((x["udid"] for v in d.values() for x in v), "iPhone"))')"

test-dart: ## Run pure-Dart package tests
	@for p in $(DART_PKGS); do echo "== $$p"; (cd $$p && TZ=$(TEST_TZ) $(DART) test) || exit 1; done

test-flutter: sync-fixtures ## Run Flutter package and demo tests
	@for p in $(FLUTTER_PKGS); do echo "== $$p"; (cd $$p && TZ=$(TEST_TZ) $(FLUTTER) test --exclude-tags real_service) || exit 1; done

analyze: sync-fixtures ## Analyze all Dart and Flutter packages
	@for p in $(DART_PKGS); do echo "== $$p"; (cd $$p && $(DART) analyze) || exit 1; done
	$(FLUTTER) analyze $(FLUTTER_PKGS)

# Opt-in real-service lane (docs/test/MOBILE.md). The repo ships no sync stack: point it at your own.
test-sync-service: ## Real PowerSync round trip; needs BOND_SYNC_SERVICE_URL, _POSTGRES_URL, _API_URL, _API_TOKEN (else prints what is missing, exits 0)
	@missing=""; for v in BOND_SYNC_SERVICE_URL BOND_SYNC_POSTGRES_URL BOND_SYNC_API_URL BOND_SYNC_API_TOKEN; do \
	  [ -n "$$(printenv $$v)" ] || missing="$$missing $$v"; done; \
	if [ -n "$$missing" ]; then echo "test-sync-service: not run. Missing:$$missing"; echo "See docs/test/MOBILE.md, 'The real-service sync lane'."; exit 0; fi; \
	cd packages/bond_tasks_powersync && TZ=$(TEST_TZ) $(FLUTTER) test -t real_service test/real_service_test.dart
