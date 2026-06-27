from __future__ import annotations

from datetime import date
from typing import Protocol

from custom_components.mojelektro import _bootstrap  # noqa: F401
from mojelektro import IntervalReading, ReadingTypeInfo


class Sink(Protocol):
    """Sink contract.

    Implementations consume one batch of readings for one (usage_point, reading_type)
    key and persist them somewhere. Sinks raise on hard failures; the dispatcher
    surfaces failures to the coordinator so per-point `last_synced_end` doesn't
    advance for points whose sinks failed.
    """

    async def write(
        self,
        usage_point: str,
        reading_type: ReadingTypeInfo,
        readings: list[IntervalReading],
        *,
        replace_window: tuple[date, date] | None = None,
    ) -> None: ...
