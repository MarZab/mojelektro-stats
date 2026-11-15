"""Load the repo's ``.env`` into ``os.environ`` for standalone CLI runs.

Only the ``python -m cli`` entry point calls this — tests invoke ``app``
directly and never see a developer's real token or usage point.
Already-set environment variables win over the file.
"""

from __future__ import annotations

import os
from collections.abc import MutableMapping
from pathlib import Path

USAGE_POINT_ENVVAR = "MOJELEKTRO_USAGE_POINT"

DOTENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def parse_dotenv(text: str) -> dict[str, str]:
    """Parse ``KEY=value`` lines. Ignores blanks, ``#`` comments and an
    optional ``export`` prefix; strips matching surrounding quotes."""
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def load_dotenv(path: Path = DOTENV_PATH, environ: MutableMapping[str, str] | None = None) -> None:
    """Copy values from ``path`` into ``environ`` without overriding."""
    target = os.environ if environ is None else environ
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return
    for key, value in parse_dotenv(text).items():
        target.setdefault(key, value)
