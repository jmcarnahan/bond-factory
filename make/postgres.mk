# Throwaway local Postgres for the `postgres`-marked tests (Homebrew binaries; never used in CI).
PG_BIN ?= /opt/homebrew/bin
PG_LIBS ?= libs/bond_jobs libs/bond_tasks_py
PG_URL = postgresql+psycopg://postgres@127.0.0.1:55432/bond_test

.PHONY: pg-up pg-down test-pg

pg-up: ## Start a throwaway Postgres in tmp/pg on 127.0.0.1:55432 (creates db bond_test)
	@mkdir -p tmp
	@test -f tmp/pg/PG_VERSION || $(PG_BIN)/initdb -D tmp/pg -U postgres --auth=trust >/dev/null
	@$(PG_BIN)/pg_ctl -D tmp/pg status >/dev/null 2>&1 || $(PG_BIN)/pg_ctl -D tmp/pg -o "-p 55432 -k /tmp -c listen_addresses=127.0.0.1" -l tmp/pg.log -w start
	@$(PG_BIN)/psql -h /tmp -p 55432 -U postgres -tAc "select 1 from pg_database where datname='bond_test'" | grep -q 1 || $(PG_BIN)/createdb -h /tmp -p 55432 -U postgres bond_test
	@echo "postgres up: $(PG_URL)"

pg-down: ## Stop the throwaway Postgres (no error if it is not running)
	@$(PG_BIN)/pg_ctl -D tmp/pg -m fast stop >/dev/null 2>&1 || true
	@echo "postgres stopped"

test-pg: ## Run the postgres-marked tests of PG_LIBS against the throwaway Postgres (make pg-up first)
	@for l in $(PG_LIBS); do echo "== $$l"; (cd $$l && BOND_TEST_POSTGRES_URL=$(PG_URL) ../../.venv/bin/python -m pytest -q -m postgres; rc=$$?; [ $$rc -eq 0 ] || [ $$rc -eq 5 ]) || exit 1; done
