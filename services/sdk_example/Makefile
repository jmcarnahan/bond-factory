PY ?= ../../.venv/bin/python
T ?=

.PHONY: test lint serve migrate
test:
	$(PY) -m pytest -q $(T)

lint:
	../../.venv/bin/ruff check sdk_example tests alembic

serve:
	mkdir -p out
	../../.venv/bin/uvicorn sdk_example.main:create_app --factory --port 8012 --reload

migrate:
	../../.venv/bin/alembic upgrade head
