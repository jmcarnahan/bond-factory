"""Label tooling: vision-model reference labels for roofs, with two independent runs per house (plan D4).

A port of the 2026-11-23 labelling code with no address handling: houses are opaque ids and directories, the entry
point (``python -m tools.roof_eval.label``) cannot spend money without --spend-cap and --confirm-spend, and the API key
is read only from the environment. See compare.py for the agreement rule and tools/roof_eval/README.md.
"""
