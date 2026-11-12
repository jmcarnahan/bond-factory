DART ?= dart
T ?=
WEB_OUT ?= $(shell mktemp -d)

# Tests run in one fixed zone (CI uses the same); a UTC machine would hide naive-timestamp bugs.
test: export TZ := America/Los_Angeles

.PHONY: test test-web analyze
test:
	$(DART) test $(T)

# Compiles the browser alert for the web (dart2js). No browser needed; not part of `test`.
test-web:
	$(DART) compile js -o $(WEB_OUT)/web_check.js tool/web_check.dart
	@echo "test-web: compiled OK"

analyze:
	$(DART) analyze
