"""The plane-based model imports and runs the CGAL-free paths without ``compas_cgal`` (plan D3/D5)."""

import subprocess
import sys
import textwrap

BLOCK = "import sys; sys.modules['compas_cgal'] = None; sys.modules['compas_cgal.straight_skeleton_2'] = None\n"


def _run(code: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", BLOCK + textwrap.dedent(code)], check=False, capture_output=True,
                          text=True, timeout=120)


def test_model_modules_import_without_cgal():
    r = _run("""
        import roof_measure.ringgeom, roof_measure.model, roof_measure.planes_model, roof_measure.classify
        import roof_measure.skeleton  # the module itself imports lazily too
        assert "compas_cgal" not in [m for m, v in sys.modules.items() if v is not None]
    """)
    assert r.returncode == 0, r.stderr


def test_flat_and_shed_blocks_build_without_cgal():
    r = _run("""
        from roof_measure.ringgeom import block_geometry
        sq = [(0, 0), (30, 0), (30, 20), (0, 20)]
        flat = block_geometry("flat", sq, 0.0)
        shed = block_geometry("shed", sq, 4.0, aspect_deg=180.0)
        assert abs(flat["facets"][0]["area"] - 600.0) < 1e-6
        assert shed["facets"][0]["area"] > 600.0
    """)
    assert r.returncode == 0, r.stderr


def test_hip_without_cgal_fails_only_at_the_call():
    r = _run("""
        from roof_measure.ringgeom import block_geometry
        try:
            block_geometry("hip", [(0, 0), (30, 0), (30, 20), (0, 20)], 6.0)
        except ImportError:
            print("import-error-at-call")
    """)
    assert r.returncode == 0, r.stderr
    assert "import-error-at-call" in r.stdout


def test_old_skeleton_names_still_reexported():
    from roof_measure import ringgeom, skeleton

    for name in ("Pt", "signed_area", "open_ring", "rect_fit", "measure", "split_footprint", "shed_roof_edges",
                 "block_geometry"):
        assert getattr(skeleton, name) is getattr(ringgeom, name)
