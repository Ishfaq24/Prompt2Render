"""Shared Jinja2 template environment, so every route module renders
through the same instance rather than each creating its own."""
from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
