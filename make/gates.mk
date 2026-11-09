# Repo-wide gates.
.PHONY: gates consumer-check

gates: ## Run every repo gate (popups, ui tokens, boundaries, line cap, public hygiene)
	bash tool/no_popups_gate.sh --enforce
	bash tool/ui_token_gate.sh
	bash tool/boundary_gate.sh
	bash tool/line_cap_gate.sh
	bash tool/public_hygiene.sh --worktree

consumer-check: ## Resolve each Dart package outside the workspace
	bash tool/consumer_check.sh
