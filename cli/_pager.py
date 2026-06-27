"""Tiny pager for the interactive readings view.

Renders a header once, then pages through data lines. Keys:
  - SPACE        → next batch
  - q  / Ctrl-C  → quit
  - ESC          → caller decides (returned as "back" so the readings
                   command can pop back to the type picker)

POSIX-only (uses termios). The CLI's interactive path is gated on
``sys.stdin.isatty()`` so non-TTY runs never enter this code.
"""

from __future__ import annotations

import select
import shutil
import sys
import termios
import tty
from typing import Literal

PagerAction = Literal["next", "quit", "back"]
PagerResult = Literal["quit", "back", "next_window"]


def read_key() -> PagerAction | None:
    """Read one key in raw mode. Returns the semantic action or None."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            # Lone ESC vs. start of an escape sequence (arrow keys etc).
            # If more bytes follow within 50ms, drain them and ignore.
            if select.select([sys.stdin], [], [], 0.05)[0]:
                while select.select([sys.stdin], [], [], 0)[0]:
                    sys.stdin.read(1)
                return None
            return "back"
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    if ch == " ":
        return "next"
    if ch in ("q", "Q", "\x03"):
        return "quit"
    return None


def paginate(
    header_lines: list[str],
    data_lines: list[str],
    *,
    footer_lines: list[str] | None = None,
) -> PagerResult:
    """Page through `data_lines` after printing `header_lines` once.

    `footer_lines` (e.g. a window banner) is printed once when the pager
    first reaches the end of the data — between the last row and the
    prompt — and stays on screen as the user pages onwards.

    Returns:
      - "quit"        — q / Ctrl-C
      - "back"        — ESC
      - "next_window" — SPACE pressed at end-of-data (caller should fetch
                        the next interval and call paginate() again)
    """
    height = shutil.get_terminal_size().lines
    overhead = len(header_lines) + len(footer_lines or []) + 2
    page_size = max(5, height - overhead)

    for line in header_lines:
        sys.stdout.write(line + "\n")
    sys.stdout.flush()

    idx = 0
    total = len(data_lines)
    footer_printed = False
    while True:
        end = min(idx + page_size, total)
        for line in data_lines[idx:end]:
            sys.stdout.write(line + "\n")
        idx = end
        if idx >= total and footer_lines and not footer_printed:
            for line in footer_lines:
                sys.stdout.write(line + "\n")
            footer_printed = True
        sys.stdout.write(_prompt_for(idx, total))
        sys.stdout.flush()
        action: PagerAction | None = None
        while action is None:
            action = read_key()
        # Erase the prompt line so the next batch starts on a clean row.
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()
        if action == "quit":
            return "quit"
        if action == "back":
            return "back"
        # action == "next"
        if idx >= total:
            return "next_window"


def _prompt_for(idx: int, total: int) -> str:
    if idx >= total:
        return "-- end -- (space=next interval, q=quit, esc=re-pick) "
    return f"-- {total - idx} more rows -- (space=next, q=quit, esc=re-pick) "
