FLUTTER ?= flutter
T ?=

# Some tests read a UTC clock in the viewer's zone; CI sets the same zone.
test: export TZ := America/Los_Angeles

.PHONY: test analyze
test:
	$(FLUTTER) test $(T)

analyze:
	$(FLUTTER) analyze
