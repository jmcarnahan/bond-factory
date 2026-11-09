# roof_measure service. `make setup` once, then `make test`, `make measure ADDR="..."`.
# Module venv from `make setup`, else the root workspace venv (`uv sync --all-packages`, what CI uses).
VENV := $(if $(wildcard .venv/bin/python),.venv,../../.venv)
PY := $(VENV)/bin/python
# real sites: local/sites.json
ADDR ?= 100 Example Ave, Sampletown, CA 90000

.PHONY: setup test lint measure serve
setup:  # always the module venv, never the root fallback
	uv venv .venv --python 3.12 --seed >/dev/null || python3 -m venv .venv
	uv pip install --python .venv/bin/python -e ".[dev]" || .venv/bin/pip install -e ".[dev]"

test:
	$(PY) -m pytest -q

lint:
	$(VENV)/bin/ruff check roof_measure tests

measure:
	$(VENV)/bin/roof-measure measure "$(ADDR)" --out out/

serve:
	$(VENV)/bin/uvicorn roof_measure.api:app --port 8011 --reload
