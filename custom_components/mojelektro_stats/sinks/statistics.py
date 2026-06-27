"""StatisticsSink: import historical readings into HA's long-term statistics.

Calls `async_add_external_statistics` once per (usage_point, reading_type) batch.
HA's recorder upserts on `(statistic_id, start_ts)`, so re-importing the same
hour is idempotent during normal sync. Manual backfill passes a `replace_window`
so existing rows in that half-open date range are deleted first — stale hours
are removed and cumulative energy baselines stay correct.

HA requires statistics timestamps at the top of the hour. Source readings are
15-minute samples (KOLICINA — per-interval deltas) or 24-hour state (STANJE —
cumulative meter total). Both need different handling:
- Energy 15-min (A_/R_ KOLICINA): aggregate the 4 quarter-hour values into a
  single hourly delta, then accumulate forward from the last sum already
  stored in HA. (Without that baseline, each chunked batch restarts cumulative
  at 0 and HA reads the boundary as a negative-consumption meter reset.)
- Energy daily (A_/R_ STANJE): each value is already the cumulative meter
  total; `sum = value` directly, no accumulation.
- Power (P_/Q_): arithmetic mean across the 4 fifteen-minute samples.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, time
from typing import Final

from homeassistant.components.recorder.db_schema import Statistics, StatisticsMeta
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
)
from homeassistant.components.recorder.util import get_instance, session_scope
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from sqlalchemy import delete, select

from custom_components.mojelektro_stats import _bootstrap  # noqa: F401
from custom_components.mojelektro_stats._naming import (
    slug_reading_type,
    slug_usage_point,
    unit,
    unit_class,
)
from custom_components.mojelektro_stats.const import STATISTIC_ID_PREFIX
from mojelektro_api import IntervalReading, ReadingTypeInfo

_LOGGER: Final = logging.getLogger(__name__)
_VRSTA_STATE: Final = "STANJE"


class StatisticsSink:
    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        # In-memory baseline cache: maps statistic_id -> (last_hour_written,
        # final_cumulative). Lets back-to-back chunks within a single coordinator
        # cycle pick up exactly where the previous chunk's cumulative left off,
        # without racing the recorder's async write queue. The stored hour also
        # prevents double-counting when API fetch windows overlap on their end
        # date (each chunk's start equals the previous chunk's end).
        self._tail: dict[str, tuple[datetime, float]] = {}

    async def write(
        self,
        usage_point: str,
        reading_type: ReadingTypeInfo,
        readings: list[IntervalReading],
        *,
        replace_window: tuple[date, date] | None = None,
    ) -> None:
        if not readings:
            return
        unit_str = unit(reading_type)
        unit_class_str = unit_class(reading_type)
        prefix = reading_type.name.split("_", 1)[0]
        is_energy = prefix in ("A", "R")
        is_state = reading_type.vrsta == _VRSTA_STATE
        # Both KOLICINA (delta) and STANJE (cumulative state) feed `sum`.
        # Power types (P/Q) are instantaneous samples -> arithmetic mean.
        has_sum = is_energy

        # HA's statistic_id regex (VALID_STATISTIC_ID) allows only [a-z0-9_]
        # in each half — flatten the dash-friendly slug we use for unique_ids.
        up_slug = slug_usage_point(usage_point)
        rt_slug = slug_reading_type(reading_type).replace("-", "_")
        statistic_id = f"{STATISTIC_ID_PREFIX}:{up_slug}_{rt_slug}"
        if replace_window is not None:
            window_start, window_stop = _window_to_datetimes(replace_window)
            cached = self._tail.get(statistic_id)
            if cached is not None:
                cached_last_hour, _ = cached
                if window_start <= cached_last_hour < window_stop:
                    del self._tail[statistic_id]
            await self._delete_statistics_in_window(statistic_id, window_start, window_stop)

        metadata = StatisticMetaData(
            mean_type=(StatisticMeanType.NONE if has_sum else StatisticMeanType.ARITHMETIC),
            has_sum=has_sum,
            name=f"{usage_point} {reading_type.naziv or reading_type.opis}",
            source=STATISTIC_ID_PREFIX,
            statistic_id=statistic_id,
            unit_class=unit_class_str,
            unit_of_measurement=unit_str,
        )

        hourly: dict[datetime, list[float]] = defaultdict(list)
        for r in readings:
            ts = _parse_ts(r.get("timestamp"))
            if ts is None:
                continue
            value = _parse_value(r.get("value"))
            if value is None:
                continue
            hourly[_truncate_to_hour(ts)].append(value)

        if not hourly:
            return

        first_hour = min(hourly)
        baseline = 0.0
        skip_through: datetime | None = None
        if has_sum and not is_state:
            from_cache, skip_through = self._resolve_baseline(statistic_id, first_hour)
            if from_cache is not None:
                baseline = from_cache
            else:
                # No usable in-memory anchor — fall back to the recorder.
                # `async_add_external_statistics` is async-queued, so during
                # a single coordinator cycle the just-written rows may not be
                # in the DB yet; the cache above is the fast path.
                baseline, skip_through = await self._previous_sum_before(
                    statistic_id, first_hour
                )

        if skip_through is not None:
            hourly = {hour: values for hour, values in hourly.items() if hour > skip_through}
            if not hourly:
                return
            first_hour = min(hourly)

        cumulative = baseline
        data: list[StatisticData] = []
        for hour in sorted(hourly):
            values = hourly[hour]
            datum = StatisticData(start=hour)
            if is_state:
                # STANJE: each reading is the meter's lifetime total at that
                # moment. Pick the latest sample within the bucket (typically
                # just one for 24 h period) and write it through.
                datum["sum"] = round(max(values), 4)
            elif has_sum:
                cumulative += sum(values)
                datum["sum"] = round(cumulative, 4)
            else:
                datum["mean"] = round(sum(values) / len(values), 4)
            data.append(datum)

        async_add_external_statistics(self._hass, metadata, data)
        if has_sum and not is_state:
            # Remember our final cumulative so the next chunk in this cycle
            # can pick up without a recorder round-trip.
            self._tail[statistic_id] = (max(hourly), cumulative)
        _LOGGER.debug(
            "Imported %d hourly statistics rows for %s (from %d raw samples, baseline=%s)",
            len(data),
            statistic_id,
            sum(len(v) for v in hourly.values()),
            baseline,
        )

    def _resolve_baseline(
        self, statistic_id: str, first_hour: datetime
    ) -> tuple[float | None, datetime | None]:
        """Use the in-memory tail when continuing a chunked import.

        Returns ``(None, None)`` when the cache is empty or when the cached
        last hour is after ``first_hour`` (importing earlier history). When the
        cached last hour equals ``first_hour`` the API window overlap is in
        effect: keep the cumulative baseline but skip re-processing that hour.
        """
        cached = self._tail.get(statistic_id)
        if cached is None:
            return None, None
        cached_last_hour, cached_sum = cached
        if cached_last_hour > first_hour:
            return None, None
        return cached_sum, cached_last_hour

    async def _previous_sum_before(
        self, statistic_id: str, first_hour: datetime
    ) -> tuple[float, datetime | None]:
        """Return the stored ``sum`` and hour for the latest row strictly before
        ``first_hour``. Falls back to ``(0.0, None)`` when there is no prior row.
        """
        recorder = get_instance(self._hass)
        return await recorder.async_add_executor_job(
            _sum_before_first_hour,
            recorder,
            statistic_id,
            first_hour,
        )

    async def _delete_statistics_in_window(
        self,
        statistic_id: str,
        window_start: datetime,
        window_stop: datetime,
    ) -> None:
        """Remove long-term statistics rows in ``[window_start, window_stop)``."""
        recorder = get_instance(self._hass)
        await recorder.async_add_executor_job(
            _delete_statistics_in_window,
            recorder,
            statistic_id,
            window_start,
            window_stop,
        )


def _truncate_to_hour(ts: datetime) -> datetime:
    return ts.replace(minute=0, second=0, microsecond=0)


def _window_to_datetimes(window: tuple[date, date]) -> tuple[datetime, datetime]:
    start, stop = window
    return (
        datetime.combine(start, time.min, tzinfo=dt_util.UTC),
        datetime.combine(stop, time.min, tzinfo=dt_util.UTC),
    )


def _delete_statistics_in_window(
    instance: object,
    statistic_id: str,
    window_start: datetime,
    window_stop: datetime,
) -> None:
    start_ts = window_start.timestamp()
    stop_ts = window_stop.timestamp()
    with session_scope(session=instance.get_session()) as session:
        row = session.execute(
            select(StatisticsMeta.id).where(StatisticsMeta.statistic_id == statistic_id)
        ).one_or_none()
        if row is None:
            return
        metadata_id = row[0]
        session.execute(
            delete(Statistics).where(
                Statistics.metadata_id == metadata_id,
                Statistics.start_ts >= start_ts,
                Statistics.start_ts < stop_ts,
            )
        )


def _sum_before_first_hour(
    instance: object,
    statistic_id: str,
    first_hour: datetime,
) -> tuple[float, datetime | None]:
    """Return ``(sum, hour)`` for the latest statistics row before ``first_hour``."""
    first_ts = first_hour.timestamp()
    with session_scope(session=instance.get_session()) as session:
        row = session.execute(
            select(StatisticsMeta.id).where(StatisticsMeta.statistic_id == statistic_id)
        ).one_or_none()
        if row is None:
            return 0.0, None
        metadata_id = row[0]
        stat_row = session.execute(
            select(Statistics.start_ts, Statistics.sum)
            .where(Statistics.metadata_id == metadata_id)
            .where(Statistics.start_ts < first_ts)
            .order_by(Statistics.start_ts.desc())
            .limit(1)
        ).one_or_none()
        if stat_row is None:
            return 0.0, None
        start_ts, last_sum = stat_row
        if last_sum is None:
            return 0.0, None
        return float(last_sum), datetime.fromtimestamp(start_ts, tz=dt_util.UTC)


def _parse_ts(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = dt_util.parse_datetime(value)
    if parsed is None:
        return None
    return dt_util.as_utc(parsed)


def _parse_value(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


