# Python service targets.
.PHONY: test-service setup-service

test-service: ## Run the roof_measure service tests
	$(MAKE) -C services/roof_measure test

setup-service: ## Create the roof_measure virtualenv
	$(MAKE) -C services/roof_measure setup
