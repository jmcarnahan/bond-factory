# Adopter lane: run an adopting app's own battery against this working tree (docs/sdk/adopter-check.md).
ADOPTER_PY ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

.PHONY: adopter-check test-adopter-lane

adopter-check: ## Run an adopting app's battery against this tree: APP=<checkout> [CONFIG=<file>] [SUITE=<name>] [KEEP=1]
	@test -n "$(APP)" || { echo "usage: make adopter-check APP=<path to the app checkout> [CONFIG=<file>] [SUITE=<name>] [KEEP=1]"; exit 2; }
	@$(ADOPTER_PY) tool/adopter_check.py --app "$(APP)" --bond "$(CURDIR)" $(if $(CONFIG),--config "$(CONFIG)") $(if $(SUITE),--suite "$(SUITE)") $(if $(KEEP),--keep)

test-adopter-lane: ## Self-test the adopter lane against the stub app
	$(ADOPTER_PY) -m unittest discover -s tool/tests -v
