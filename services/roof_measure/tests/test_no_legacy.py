"""The legacy roof paths are gone: nothing live loads them, the old entry points refuse, the files do not exist."""

import subprocess
import sys
from pathlib import Path

import pytest

from roof_measure import library

PKG = Path(library.__file__).parent
DELETED = ("blocks", "classify", "skeleton", "skeleton_gable", "skeleton_guard", "ringgeom", "model_cleanup",
           "model_slivers", "planes", "planes_net", "planes_straight", "planes_tidy", "planes_gaps", "planes_lines",
           "planes_model", "planes_only", "planes_envelope", "agent", "agent_pick", "agent_tools", "verify",
           "verify_llm", "verify_merge", "verify_tools", "solar", "footprint_solar", "api", "auth", "jobs", "keys",
           "normalize", "results", "runner", "service", "settings", "cli", "synth", "synth_extra", "render", "fixtures")


@pytest.mark.parametrize("target", ["roof_measure.pipeline", "roof_measure.engine", "roof_measure.lot",
                                    "roof_measure.library"])
def test_importing_the_live_path_loads_no_deleted_module(target):
    code = (f"import sys, importlib; importlib.import_module({target!r}); "
            f"bad = [n for n in sys.modules if n.startswith('roof_measure.') and n.split('.')[1] in {DELETED!r}]; "
            "print(bad); sys.exit(1 if bad else 0)")
    r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stdout + r.stderr


def test_the_deleted_files_do_not_exist():
    assert [n for n in DELETED if (PKG / f"{n}.py").exists()] == []
    assert not (PKG.parent / "Dockerfile").exists() and not (PKG.parent / "railway.toml").exists()


@pytest.mark.parametrize("kw", [{"engine": "blocks"}, {"method": "auto"}, {"hints": {}}, {"verify": False},
                                {"anthropic_api_key": "k"}, {"google_solar_api_key": "k"}])
def test_the_removed_arguments_raise_type_error(tmp_path, kw):
    with pytest.raises(TypeError):
        library.measure("1 Example St", cache_dir=tmp_path, **kw)


def test_a_measurement_needs_none_of_the_removed_dependencies(tmp_path):
    """The dev venv still has these packages: block them in a clean interpreter so a lazy import would fail here."""
    from house_helpers import house

    folder = house(tmp_path)
    code = ("import sys\n"
            "for n in ('anthropic', 'compas_cgal', 'compas', 'fastapi', 'uvicorn', 'httpx', 'matplotlib'):\n"
            "    sys.modules[n] = None\n"
            "from roof_measure import library\n"
            f"env = library.measure('', points_path={str(folder)!r}, cache_dir={str(tmp_path / 'c')!r}, isolate=False)\n"
            "assert env['contract'] == 'bond.roof_model/0.2' and env['totals']['area_sqft'] > 0\n")
    r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stderr[-800:]
