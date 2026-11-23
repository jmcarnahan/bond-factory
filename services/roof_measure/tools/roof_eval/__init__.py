"""Roof regression scorer and eval harness (generic, public, data-free).

Data lives outside the repo under ``$ROOF_EVAL_DATA`` (see ``data.py`` for the layout). Entry point:
``python -m tools.roof_eval --help`` (the roof-eval targets in the module Makefile wrap it).
"""

SCORER_VERSION = "1"
