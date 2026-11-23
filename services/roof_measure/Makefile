# roof_measure service. `make setup` once, then `make test`, `make serve`, `make measure ADDR="..."`.
# Module venv from `make setup`, else the root workspace venv (`uv sync --all-packages`, what CI uses).
VENV := $(if $(wildcard .venv/bin/python),.venv,../../.venv)
PY := $(VENV)/bin/python
# real sites: local/sites.json
ADDR ?= 100 Example Ave, Sampletown, CA 90000

.PHONY: setup test lint measure serve fixtures eval
setup:  # always the module venv, never the root fallback
	uv venv .venv --python 3.12 --seed >/dev/null || python3 -m venv .venv
	uv pip install --python .venv/bin/python -e ".[dev,service,render]" || .venv/bin/pip install -e ".[dev,service,render]"

test:
	$(PY) -m pytest -q

lint:
	$(VENV)/bin/ruff check roof_measure tests tools

measure:
	$(VENV)/bin/roof-measure measure "$(ADDR)" --out out/

# Local dev server: no auth, loopback only, debug fixture routes on. Production sets ROOF_MEASURE_TOKEN instead.
serve:
	ROOF_MEASURE_AUTH=off ROOF_MEASURE_HOST=127.0.0.1 ROOF_MEASURE_DEBUG=1 \
	$(VENV)/bin/uvicorn roof_measure.api:app --host 127.0.0.1 --port $${PORT:-8011}

# Regenerate the synthetic fixtures and the four 0.2 envelopes in ../../fixtures (deterministic).
fixtures:
	$(PY) -m roof_measure.synth_envelopes

# Offline rule-method evaluation of saved LiDAR block files: `make eval BLOCKS=<file-or-dir> [ARGS="--json f.json --svg dir"]`
eval:
	@test -n "$(BLOCKS)" || { echo "usage: make eval BLOCKS=<file-or-dir> [ARGS=...]"; exit 2; }
	$(PY) -m tools.eval_blocks $(BLOCKS) $(ARGS)

# ---- roof regression harness (tools/roof_eval; the data root is $ROOF_EVAL_DATA, never in this repo) ----
# roof-eval [SPLIT=tuning|demo|heldout|all] [ENGINE=library|results-dir:<dir>|"<cmd> {house_dir} {out_json}"] [BASELINE=name]
#           [JOBS=n] [GATES=gates.json] [PRICE=rules.json] [TWICE=1] [OUT=dir] [ARGS="--where roof_class=flat --limit 5"]
.PHONY: roof-reference roof-eval roof-baseline roof-blind roof-blind-score roof-sweep roof-eval-test
roof-eval:
	$(PY) -m tools.roof_eval eval --split $(if $(SPLIT),$(SPLIT),tuning) $(if $(ENGINE),--engine "$(ENGINE)") \
	  $(if $(BASELINE),--baseline $(BASELINE)) $(if $(JOBS),--jobs $(JOBS)) $(if $(GATES),--gates $(GATES)) \
	  $(if $(PRICE),--price-rules $(PRICE)) $(if $(OUT),--out $(OUT)) $(if $(TWICE),--twice) $(if $(NO_GATES),--no-gates) $(ARGS)

# roof-baseline NAME=x CONFIRM=1 [RUN=out/roof-eval/<run>]: freeze metrics + results under <data>/baselines/x
roof-baseline:
	@test -n "$(NAME)" || { echo "usage: make roof-baseline NAME=x CONFIRM=1 [RUN=dir]"; exit 2; }
	$(PY) -m tools.roof_eval baseline --name $(NAME) $(if $(filter 1,$(CONFIRM)),--confirm) $(if $(RUN),--run $(RUN))

# roof-blind N=20 SEED=1 CAND="a=<dir> b=baseline:x" OUT=<images dir> KEY=<key.json outside OUT> [SPLIT=heldout]
roof-blind:
	@test -n "$(OUT)" -a -n "$(KEY)" -a -n "$(CAND)" || { echo "usage: make roof-blind N= SEED= CAND=\"a=dir b=baseline:x\" OUT=dir KEY=file [SPLIT=heldout]"; exit 2; }
	$(PY) -m tools.roof_eval blind --split $(if $(SPLIT),$(SPLIT),heldout) --n $(if $(N),$(N),20) --seed $(if $(SEED),$(SEED),1) \
	  $(foreach c,$(CAND),--cand $(c)) --out $(OUT) --key-out $(KEY) $(ARGS)

# roof-blind-score GRADES=grades.tsv KEY=key.json [GRADERS=a,b]
roof-blind-score:
	@test -n "$(GRADES)" -a -n "$(KEY)" || { echo "usage: make roof-blind-score GRADES=grades.tsv KEY=key.json"; exit 2; }
	$(PY) -m tools.roof_eval blind-score --grades $(GRADES) --key $(KEY) $(if $(GRADERS),--graders $(GRADERS))

# roof-sweep HOUSES=<dir of house dirs | list file> ENGINE=... [JOBS=n]: truth-free automation / verdict / failure table
roof-sweep:
	@test -n "$(HOUSES)" || { echo "usage: make roof-sweep HOUSES=dir ENGINE=..."; exit 2; }
	$(PY) -m tools.roof_eval sweep --houses $(HOUSES) $(if $(ENGINE),--engine "$(ENGINE)") $(if $(JOBS),--jobs $(JOBS)) $(if $(OUT),--out $(OUT)) $(ARGS)

# roof-reference [REBUILD=1]: check (exit 1 when stale) or rebuild the frozen reference points, rule ref-v1 + parameter hash
roof-reference:
	$(PY) -m tools.roof_eval reference $(if $(REBUILD),--rebuild)

roof-eval-test:
	$(PY) -m pytest -q tests/test_roof_eval_*.py

# roof-synth ENGINE=... [ONLY=gable] [JOBS=n] [GATES=g.json]: gate 9 over the synthetic roofs. ENGINE=oracle exits 1 by design
# (the oracle answers below 4 pts/m2); `make roof-synth ENGINE=oracle ARGS=--selftest` is the scorer self-test (exit 0 iff only those fail)
.PHONY: roof-synth
roof-synth:
	$(PY) -m tools.roof_eval synth $(if $(ENGINE),--engine "$(ENGINE)") $(if $(JOBS),--jobs $(JOBS)) $(if $(OUT),--out $(OUT)) \
	  $(foreach o,$(ONLY),--only $(o)) $(if $(GATES),--gates $(GATES)) $(ARGS)
