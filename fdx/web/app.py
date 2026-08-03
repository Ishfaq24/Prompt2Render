"""The FastAPI application: mounts every route module and static assets.

Every direct-import call that can raise SystemExit (project.parse_script,
project.new_project, visuals.import_sections, ...) is wrapped in an
explicit try/except at its own call site across the route modules --
NOT behind a blanket exception handler here. Starlette's
add_exception_handler() only accepts Exception subclasses; SystemExit is a
BaseException and registering a handler for it raises AssertionError at
app-startup (confirmed directly against this Starlette version), so
per-call-site handling is not just tidier, it is the only option.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import (routes_files, routes_pipeline, routes_projects,
               routes_review, routes_scenes, routes_script, routes_upload)

app = FastAPI(title="fdx-studio")

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

for router in (routes_projects.router, routes_script.router,
              routes_pipeline.router, routes_scenes.router,
              routes_upload.router, routes_review.router,
              routes_files.router):
    app.include_router(router)
