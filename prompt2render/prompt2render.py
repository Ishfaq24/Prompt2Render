"""prompt2render CLI backward-compatibility shim.

Authoritative CLI implementation is located in prompt2render.cli.
"""
from __future__ import annotations

from prompt2render.cli import *
from prompt2render.cli import main

if __name__ == "__main__":
    main()