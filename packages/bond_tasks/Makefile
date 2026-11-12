DART ?= dart
T ?=

.PHONY: test analyze

# The stage fixture cases are written for Los Angeles, so the test target always runs in that zone (it
# replaces a TZ from the environment) and the stage tests never skip silently. Their skip guard stays only
# as a safety net for `dart test` run by hand.
test: export TZ = America/Los_Angeles
test:
	$(DART) test $(T)

analyze:
	$(DART) analyze
