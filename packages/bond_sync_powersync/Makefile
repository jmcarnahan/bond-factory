FLUTTER ?= flutter
DART ?= dart
T ?=

# Tests run in one fixed zone (CI uses the same); a UTC machine would hide naive-timestamp bugs.
test: export TZ := America/Los_Angeles

.PHONY: test analyze web-compile
test:
	$(FLUTTER) test $(T)

analyze:
	$(FLUTTER) analyze

# Fails when any lib/ file but store_files_io.dart imports dart:io (dart2js compiles dart:io too, so the compile alone
# cannot catch it), then compiles the opener to JavaScript (about 2 s). Nothing is run in a browser.
web-compile:
	@if grep -rnE "(import|export)[[:space:]]+['\"]dart:(io|ffi)['\"]" lib | grep -v '^lib/src/store_files_io.dart:'; then \
	  echo "web-compile: only lib/src/store_files_io.dart may import dart:io (see lines above)"; exit 1; fi
	$(DART) compile js tool/web_compile.dart -o $${TMPDIR:-/tmp}/bond_sync_powersync_web.js
