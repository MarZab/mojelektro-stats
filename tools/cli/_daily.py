"""Pure helpers for the `daily` command: turn daily register (STANJE)
readings into per-day usage.

The API stamps each daily register reading at the local midnight *after*
the day it closes (``2026-10-25T00:00:00+02:00`` closes Oct 24). 15-minute
interval readings are likewise stamped at the end of their interval. Both
are attributed to the local date of ``timestamp - 1 s``, which also keeps
23/25-hour DST days right without any fixed 24 h arithmetic.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from mojelektro_api.models import MeterReadings
from mojelektro_api.reading_types import ReadingTypeInfo

LOCAL_TZ = ZoneInfo("Europe/Ljubljana")

# The Moj Elektro API caps one /meter-readings request at 35 days
# (mirrors MAX_FETCH_WINDOW_DAYS in the integration's const.py).
MAX_FETCH_WINDOW_DAYS = 35

STATE_VRSTA = "STANJE"


def closing_day(timestamp: str) -> date | None:
    """Local date a reading belongs to, or None for an unparseable stamp."""
    try:
        moment = datetime.fromisoformat(timestamp)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=LOCAL_TZ)
    return (moment.astimezone(LOCAL_TZ) - timedelta(seconds=1)).date()


def _parse_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _values_by_day(
    payloads: Iterable[MeterReadings], info: ReadingTypeInfo
) -> Iterator[tuple[str, date, Decimal]]:
    """Yield (timestamp, day, value) for one reading type across payloads,
    skipping duplicate timestamps (overlapping fetch chunks)."""
    raw_code = info.code.value.removeprefix("ReadingType=")
    seen: set[str] = set()
    for payload in payloads:
        for block in payload.get("intervalBlocks") or []:
            if block.get("readingType") != raw_code:
                continue
            for reading in block.get("intervalReadings") or []:
                ts = reading.get("timestamp")
                if not ts or ts in seen:
                    continue
                seen.add(ts)
                day = closing_day(ts)
                value = _parse_decimal(reading.get("value"))
                if day is not None and value is not None:
                    yield ts, day, value


def register_by_day(
    payloads: Iterable[MeterReadings], info: ReadingTypeInfo
) -> dict[date, Decimal]:
    """Closing register value per day (the latest reading wins)."""
    latest: dict[date, tuple[str, Decimal]] = {}
    for ts, day, value in _values_by_day(payloads, info):
        current = latest.get(day)
        if current is None or ts > current[0]:
            latest[day] = (ts, value)
    return {day: value for day, (_, value) in latest.items()}


def closing_hour(timestamp: str) -> datetime | None:
    """Start of the hour an interval reading belongs to, in **UTC**, using
    the same ``timestamp - 1 s`` rule as `closing_day`.

    UTC keys on purpose: aware datetimes sharing a ZoneInfo compare by wall
    time and ignore ``fold``, so the repeated 02:00 on the autumn DST day
    would collapse into one key. Ljubljana offsets are whole hours, so a UTC
    hour start is also a local hour start; convert with
    ``.astimezone(LOCAL_TZ)`` for display.
    """
    try:
        moment = datetime.fromisoformat(timestamp)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=LOCAL_TZ)
    shifted = (moment - timedelta(seconds=1)).astimezone(UTC)
    return shifted.replace(minute=0, second=0, microsecond=0)


def sum_by_hour(
    payloads: Iterable[MeterReadings], info: ReadingTypeInfo
) -> dict[datetime, Decimal]:
    """Sum of interval values per hour, keyed by UTC hour start
    (for 15-minute KOLICINA types)."""
    totals: dict[datetime, Decimal] = {}
    for ts, _, value in _values_by_day(payloads, info):
        hour = closing_hour(ts)
        if hour is not None:
            totals[hour] = totals.get(hour, Decimal(0)) + value
    return totals


def sum_by_day(payloads: Iterable[MeterReadings], info: ReadingTypeInfo) -> dict[date, Decimal]:
    """Sum of interval values per day (for 15-minute KOLICINA types)."""
    totals: dict[date, Decimal] = {}
    for _, day, value in _values_by_day(payloads, info):
        totals[day] = totals.get(day, Decimal(0)) + value
    return totals


def usage_by_day(
    registers: dict[date, Decimal], days: Iterable[date]
) -> dict[date, Decimal | None]:
    """``register[d] - register[d - 1]``; None when either side is missing."""
    usage: dict[date, Decimal | None] = {}
    for day in days:
        today = registers.get(day)
        yesterday = registers.get(day - timedelta(days=1))
        usage[day] = None if today is None or yesterday is None else today - yesterday
    return usage


def days_between(start: date, end: date) -> list[date]:
    """Inclusive list of days from start to end."""
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def fetch_range(start: date, end: date) -> tuple[date, date]:
    """API date range covering the readings needed for days start..end.

    Needs the closing reading of ``start - 1`` (stamped at ``start``
    00:00) through the closing reading of ``end`` (stamped at ``end + 1``
    00:00). One extra day on each side absorbs the API's date semantics
    and the UTC/local offset.
    """
    return start - timedelta(days=1), end + timedelta(days=2)


def chunk_window(
    start: date, end: date, max_days: int = MAX_FETCH_WINDOW_DAYS
) -> list[tuple[date, date]]:
    """Split [start, end] into consecutive windows of at most max_days."""
    chunks: list[tuple[date, date]] = []
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=max_days), end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end
    return chunks


@dataclass(frozen=True, slots=True)
class Column:
    label: str
    values: dict[date, Decimal | None]


def build_rows(days: list[date], columns: list[Column]) -> list[dict[str, Decimal | None]]:
    """One mapping per day: column label -> value (None = missing)."""
    return [{col.label: col.values.get(day) for col in columns} for day in days]


def column_totals(
    rows: list[dict[str, Decimal | None]], labels: list[str]
) -> dict[str, Decimal | None]:
    """Sum each column over the days that have a value."""
    totals: dict[str, Decimal | None] = {}
    for label in labels:
        present = [v for row in rows if (v := row.get(label)) is not None]
        totals[label] = sum(present, Decimal(0)) if present else None
    return totals
