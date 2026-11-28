# roof_measure

Role: library (`roof_measure.measure`). Address -> footprint chain + LiDAR -> plane engine -> envelope
`bond.roof_model/0.2` (model `bond.roof_model/0.1`). Python 3.12. Contract: docs/contract-0.2.md, 0.3, 0.4 (additive),
docs/contracts/roof_model.md. The block path, the agents, the verifier, Solar and the job service were removed.

## Key files (roof_measure/)
- library.py facade (measure, MeasureError); _isolate.py/_child.py child process; config.py Runtime (authoritative when set, env otherwise); text.py
- pipeline.py run_pipeline; pipeline_engine.py (data stages -> engine -> model); pipeline_stages.py data stages; pipeline_result.py PipelineResult;
  pipeline_notes.py warnings; blockset.py the per-measurement data holder; lot.py other buildings; envelope.py 0.2 result; quality.py engine quality
- model.py contract constants, totals, validate, write_model; errors.py code_for(exc); version.py PIPELINE_VERSION
- footprint.py chain; footprint_{county,osm,hull}.py links; footprint_types.py Footprint; geocode, lidar, frame, cache, deadline
- engine/: the plane engine (params.py holds every tunable); synth_points/synth_shapes: synthetic roofs for tests
- synth_engine_envelope.py, synth_envelopes.py: the engine example envelope in ../../fixtures/roof_engine

## Commands (this dir)
- `make setup` once; `make test`; one file `.venv/bin/pytest tests/test_x.py`; `make lint`; `make fixtures`; harness: `make roof-eval`, `make roof-synth`

## Rules
- New code in new modules; keep files under 400 lines.
- Deadlines: cache.fetch_bytes reads the ambient cache.deadline_scope (pipeline_engine); watchdog = deadline + 30 s.
- Never log token or address at INFO; never read tests/data/**, local/test-data/*.pts, uv.lock. Real sites: local/sites.json only; tests needing them skip; network tests need ROOF_MEASURE_NETWORK=1.
- `import roof_measure` must stay free of numpy (test_library_imports.py). matplotlib (`render` extra) and anthropic (`label` extra) are for tools/roof_eval only.
- bond-factory is public: tests use synthetic roofs only, no real address, coordinate or LiDAR.
- cache/, out/, data/ are gitignored.
