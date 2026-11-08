# Repo-wide gates.
.PHONY: gates

gates: ## Run the no-popups gate in enforce mode
	bash tool/no_popups_gate.sh --enforce
