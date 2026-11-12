DART ?= dart
T ?=

# Tests run in one fixed zone (CI uses the same); a UTC machine would hide naive-timestamp bugs.
test: export TZ := America/Los_Angeles

.PHONY: test analyze render
test:
	$(DART) test $(T)

analyze:
	$(DART) analyze

render:
	$(DART) run example/render_fixtures.dart
