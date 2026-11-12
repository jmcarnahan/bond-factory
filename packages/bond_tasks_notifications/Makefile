FLUTTER ?= flutter
T ?=

.PHONY: test analyze
# The fixture tests need the Los Angeles zone; forced so they never skip silently.
test: export TZ := America/Los_Angeles
test:
	$(FLUTTER) test $(T)

analyze:
	$(FLUTTER) analyze
