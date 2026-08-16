"""Pytest bootstrap: make the package root importable.

The bot is normally run from its own directory, so modules import as
``from util.x import y``. Adding the package root to ``sys.path`` here lets the
test suite resolve those same imports regardless of where pytest is invoked.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
