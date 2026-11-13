# Python service targets.
LIBS = $(wildcard libs/*)

.PHONY: test-service setup-service setup-py test-libs lint-libs test-example serve-example test-legacy-host

test-service: ## Run the roof_measure service tests
	$(MAKE) -C services/roof_measure test

setup-service: ## Create the roof_measure virtualenv
	$(MAKE) -C services/roof_measure setup

setup-py: ## Create the root workspace venv (uv sync --all-packages --all-extras)
	uv sync --all-packages --all-extras

test-libs: ## Run every libs/* test suite
	@for l in $(LIBS); do echo "== $$l"; $(MAKE) -C $$l test || exit 1; done

lint-libs: ## Ruff every libs/*
	@for l in $(LIBS); do echo "== $$l"; $(MAKE) -C $$l lint || exit 1; done

test-example: ## Run the sdk_example tests
	$(MAKE) -C services/sdk_example test

serve-example: ## Serve sdk_example on :8012
	$(MAKE) -C services/sdk_example serve

test-legacy-host: ## Run the legacy_host tests (a test-only host with legacy columns, wire and tables)
	$(MAKE) -C services/legacy_host test
