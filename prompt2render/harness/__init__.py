"""Prompt2Render harness — an additive research/evaluation layer over prompt2render's live pipeline.

Scope (see docs/MIGRATION_INVENTORY.md and the Stage 2-5 plan): the generation/verification/
repair loop only (script -> scene_plan -> code_artifacts -> render_artifacts -> check_results).
`voice`/`align`/`timeline`/`encode`/`finish`/`publish` stay exactly as they are, invoked directly
by prompt2render.py's existing CLI — this package does not touch that CLI or its behavior.
"""
