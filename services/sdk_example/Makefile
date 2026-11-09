PY ?= ../../.venv/bin/python
T ?=

.PHONY: test lint serve
test:
	$(PY) -m pytest -q $(T)

lint:
	../../.venv/bin/ruff check sdk_example tests

serve:
	../../.venv/bin/uvicorn sdk_example.main:app --port 8012 --reload
