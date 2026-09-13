#!/usr/bin/env python3
"""prompt2render — narrated, code-animated explainer videos, built to frame accuracy.

    python prompt2render.py new binary-search
    python prompt2render.py build binary-search
    python prompt2render.py auto binary-search
"""
from __future__ import annotations

import sys
from prompt2render.cli import main

if __name__ == "__main__":
    main()