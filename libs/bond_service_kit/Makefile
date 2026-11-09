PY ?= ../../.venv/bin/python
T ?=

.PHONY: test lint
test:
	$(PY) -m pytest -q $(T)

lint:
	../../.venv/bin/ruff check bond_service_kit tests
