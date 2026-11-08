FLUTTER ?= flutter
T ?=

.PHONY: sync-fixtures test analyze run-web build-web
sync-fixtures:
	tool/sync_fixtures.sh

test: sync-fixtures
	$(FLUTTER) test $(T)

analyze: sync-fixtures
	$(FLUTTER) analyze

run-web: sync-fixtures
	$(FLUTTER) run -d chrome

build-web: sync-fixtures
	$(FLUTTER) build web --release
