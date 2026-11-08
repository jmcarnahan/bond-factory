# Dart and Flutter targets. DART_PKGS are pure Dart; FLUTTER_PKGS need the Flutter SDK.
DART_PKGS = packages/bond_roof
FLUTTER_PKGS = packages/bond_roof_ui demos/roof_demo

.PHONY: sync-fixtures demo-web demo-ios build-web test-dart test-flutter analyze

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
	@for p in $(DART_PKGS); do echo "== $$p"; (cd $$p && $(DART) test) || exit 1; done

test-flutter: sync-fixtures ## Run Flutter package and demo tests
	@for p in $(FLUTTER_PKGS); do echo "== $$p"; (cd $$p && $(FLUTTER) test) || exit 1; done

analyze: sync-fixtures ## Analyze all Dart and Flutter packages
	@for p in $(DART_PKGS); do echo "== $$p"; (cd $$p && $(DART) analyze) || exit 1; done
	$(FLUTTER) analyze $(FLUTTER_PKGS)
