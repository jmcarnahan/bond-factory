# roof_measure service. `make setup` once, then `make test`, `make serve`, `make measure ADDR="..."`.
# Module venv from `make setup`, else the root workspace venv (`uv sync --all-packages`, what CI uses).
VENV := $(if $(wildcard .venv/bin/python),.venv,../../.venv)
PY := $(VENV)/bin/python
# real sites: local/sites.json
ADDR ?= 100 Example Ave, Sampletown, CA 90000

.PHONY: setup test lint measure serve fixtures
setup:  # always the module venv, never the root fallback
	uv venv .venv --python 3.12 --seed >/dev/null || python3 -m venv .venv
	uv pip install --python .venv/bin/python -e ".[dev,service,render]" || .venv/bin/pip install -e ".[dev,service,render]"

test:
	$(PY) -m pytest -q

lint:
	$(VENV)/bin/ruff check roof_measure tests

measure:
	$(VENV)/bin/roof-measure measure "$(ADDR)" --out out/

# Local dev server: no auth, loopback only, debug fixture routes on. Production sets ROOF_MEASURE_TOKEN instead.
serve:
	ROOF_MEASURE_AUTH=off ROOF_MEASURE_HOST=127.0.0.1 ROOF_MEASURE_DEBUG=1 \
	$(VENV)/bin/uvicorn roof_measure.api:app --host 127.0.0.1 --port $${PORT:-8011}

# Regenerate the synthetic fixtures and the four 0.2 envelopes in ../../fixtures (deterministic).
fixtures:
	$(PY) -m roof_measure.synth_envelopes
