"""Ensure the vendored mojelektro lib is importable in Home Assistant.

HA loads integration modules directly (e.g. config_flow) without always
importing this package's __init__ first, so any module that imports
``mojelektro`` must import this module before those imports.
"""

from __future__ import annotations

import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent / "lib"
_PATH = str(_LIB_DIR)
if _PATH not in sys.path:
    sys.path.insert(0, _PATH)
