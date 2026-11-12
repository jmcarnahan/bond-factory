FLUTTER ?= flutter
T ?=
# the day-view tests need this zone; export it so they never skip silently
test: export TZ := America/Los_Angeles

.PHONY: test analyze
test:
	$(FLUTTER) test $(T)

analyze:
	$(FLUTTER) analyze
