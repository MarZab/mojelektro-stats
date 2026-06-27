"""Add the vendored mojelektro_api lib to sys.path for standalone CLI runs."""

from __future__ import annotations

import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "mojelektro_stats" / "lib"
_PATH = str(_LIB_DIR)
if _PATH not in sys.path:
    sys.path.insert(0, _PATH)
