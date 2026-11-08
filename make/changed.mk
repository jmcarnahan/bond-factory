# Change-aware helpers. BASE=<ref> (default main) picks the diff base.
.PHONY: changed test-changed

changed: ## List modules affected by changes vs BASE (default main)
	bash tool/changed_modules.sh

test-changed: ## Run `make test` in each affected module
	bash tool/changed_modules.sh --test
