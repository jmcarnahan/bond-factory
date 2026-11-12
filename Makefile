# bond-factory root. Real targets live in make/*.mk; `make help` lists them.
# FLUTTER and DART come from PATH; override with `make FLUTTER=/path/to/flutter ...`
# (DART then follows FLUTTER's bin dir unless given explicitly).
FLUTTER ?= flutter
DART ?= $(if $(filter /%,$(FLUTTER)),$(dir $(FLUTTER))dart,dart)
export FLUTTER DART

.DEFAULT_GOAL := help

include make/dart.mk make/python.mk make/gates.mk make/changed.mk make/postgres.mk

.PHONY: help test
test: test-dart test-flutter test-service test-libs test-example ## Run every test suite (Dart, Flutter, Python services, libs, example)

help: ## List targets
	@grep -hE '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/:[^#]*## /\t/' | sort | awk -F'\t' '{printf "  %-16s %s\n", $$1, $$2}'
