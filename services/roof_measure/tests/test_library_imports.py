"""`import roof_measure.pipeline` stays light: no matplotlib, no web stack, no anthropic (plan L5)."""

import subprocess
import sys

LIGHT = ("import sys, roof_measure, roof_measure.pipeline, roof_measure.runner, roof_measure.errors; "
         "bad = sorted(m for m in ('matplotlib', 'fastapi', 'uvicorn', 'starlette', 'pydantic', 'anthropic') "
         "if m in sys.modules); print(bad)")


def _run(code: str) -> str:
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, check=False)
    assert res.returncode == 0, res.stderr[-800:]
    return res.stdout.strip()


def test_the_pipeline_imports_without_matplotlib_or_the_web_stack():
    assert _run(LIGHT) == "[]"


def test_the_service_path_still_imports_fastapi():
    assert _run("import sys, roof_measure.api; print('fastapi' in sys.modules)") == "True"


def test_a_bare_import_pulls_in_no_heavy_dependency():
    heavy = ("numpy", "scipy", "shapely", "compas_cgal", "requests", "anthropic", "matplotlib", "fastapi")
    code = f"import sys, roof_measure; print(sorted(m for m in {heavy!r} if m in sys.modules))"
    assert _run(code) == "[]"
