"""InfluxDBSink: write raw 15-min readings as line protocol to InfluxDB v2.

POSTs to `{url}/api/v2/write?org=...&bucket=...&precision=s`. One async httpx
client per sink instance, reused across writes.

Line shape:
    mojelektro,usage_point=<id>,reading_type=<name>,unit=<kWh|kVArh|kW|kVAr> value=<float> <unix_s>

InfluxDB upserts on `(measurement, tag-set, timestamp)`, so re-importing the
same readings is idempotent during normal sync. Manual backfill passes a
`replace_window` so existing points in that half-open date range are deleted
before the write.

401/403 from InfluxDB -> ConfigEntryAuthFailed so HA prompts the user to
re-enter the InfluxDB token via the OptionsFlow.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time
from typing import Final

import httpx
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.util import dt as dt_util

from custom_components.mojelektro_stats import _bootstrap  # noqa: F401
from custom_components.mojelektro_stats._naming import unit
from mojelektro_api import IntervalReading, ReadingTypeInfo

_LOGGER: Final = logging.getLogger(__name__)
_MEASUREMENT: Final = "mojelektro"


class InfluxDBAuthError(Exception):
    """InfluxDB rejected the token (401/403)."""


class InfluxDBConnectionError(Exception):
    """InfluxDB is unreachable or returned a transport failure."""


class InfluxDBError(Exception):
    """InfluxDB returned an unexpected error response."""


async def probe_influxdb_connection(
    http: httpx.AsyncClient,
    *,
    url: str,
    org: str,
    bucket: str,
    token: str,
) -> int:
    """Verify org/bucket access and return existing ``mojelektro`` point count."""
    base = url.rstrip("/")
    flux = (
        f'from(bucket: "{_escape_flux_string(bucket)}")\n'
        f'  |> range(start: 1970-01-01T00:00:00Z)\n'
        f'  |> filter(fn: (r) => r._measurement == "{_MEASUREMENT}")\n'
        "  |> count()"
    )
    try:
        response = await http.post(
            f"{base}/api/v2/query",
            params={"org": org},
            headers={
                "Authorization": f"Token {token}",
                "Content-Type": "application/vnd.flux",
                "Accept": "application/csv",
            },
            content=flux.encode("utf-8"),
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        raise InfluxDBConnectionError(str(exc)) from exc

    if response.status_code in (401, 403):
        raise InfluxDBAuthError(response.text[:200]) from None
    if response.status_code >= 400:
        raise InfluxDBError(f"HTTP {response.status_code}: {response.text[:200]}") from None
    return _parse_flux_count_csv(response.text)


def _parse_flux_count_csv(body: str) -> int:
    """Parse the ``count()`` column from an InfluxDB CSV query response."""
    for line in body.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split(",")
        if len(parts) < 2:
            continue
        if parts[1] == "result" and parts[-1].strip() == "_value":
            continue
        raw = parts[-1].strip()
        if not raw:
            continue
        try:
            return int(float(raw))
        except ValueError:
            continue
    return 0


def _escape_flux_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


class InfluxDBSink:
    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        url: str,
        org: str,
        bucket: str,
        token: str,
    ) -> None:
        self._http = http
        self._url = url.rstrip("/")
        self._org = org
        self._bucket = bucket
        self._token = token

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
        if replace_window is not None:
            await self._delete_points_in_window(usage_point, reading_type, replace_window)
        unit_str = unit(reading_type) or ""
        lines: list[str] = []
        for r in readings:
            ts_iso = r.get("timestamp")
            raw_value = r.get("value")
            if not ts_iso or raw_value is None:
                continue
            ts = dt_util.parse_datetime(ts_iso)
            if ts is None:
                continue
            try:
                value = round(float(raw_value), 4)
            except (TypeError, ValueError):
                continue
            unix_s = int(dt_util.as_utc(ts).timestamp())
            tags = [
                f"usage_point={_escape_tag(usage_point)}",
                f"reading_type={_escape_tag(reading_type.name)}",
            ]
            if unit_str:
                tags.append(f"unit={_escape_tag(unit_str)}")
            lines.append(f"{_MEASUREMENT},{','.join(tags)} value={value} {unix_s}")
        if not lines:
            return

        body = "\n".join(lines).encode("utf-8")
        try:
            response = await self._http.post(
                f"{self._url}/api/v2/write",
                params={
                    "org": self._org,
                    "bucket": self._bucket,
                    "precision": "s",
                },
                headers={
                    "Authorization": f"Token {self._token}",
                    "Content-Type": "text/plain; charset=utf-8",
                },
                content=body,
                timeout=30.0,
            )
        except httpx.HTTPError as exc:
            _LOGGER.warning("InfluxDB write transport error: %s", exc)
            raise

        if response.status_code in (401, 403):
            raise ConfigEntryAuthFailed("InfluxDB rejected the token") from None
        if response.status_code >= 400:
            _LOGGER.warning(
                "InfluxDB write failed (%s): %s",
                response.status_code,
                response.text[:500],
            )
            response.raise_for_status()
        _LOGGER.debug(
            "Wrote %d points to InfluxDB for %s / %s",
            len(lines),
            usage_point,
            reading_type.name,
        )

    async def _delete_points_in_window(
        self,
        usage_point: str,
        reading_type: ReadingTypeInfo,
        replace_window: tuple[date, date],
    ) -> None:
        window_start, window_stop = _window_to_datetimes(replace_window)
        predicate = (
            f'_measurement="{_MEASUREMENT}" AND '
            f'usage_point="{_escape_predicate_string(usage_point)}" AND '
            f'reading_type="{_escape_predicate_string(reading_type.name)}"'
        )
        body = {
            "start": window_start.isoformat().replace("+00:00", "Z"),
            "stop": window_stop.isoformat().replace("+00:00", "Z"),
            "predicate": predicate,
        }
        try:
            response = await self._http.post(
                f"{self._url}/api/v2/delete",
                params={"org": self._org, "bucket": self._bucket},
                headers={
                    "Authorization": f"Token {self._token}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=30.0,
            )
        except httpx.HTTPError as exc:
            _LOGGER.warning("InfluxDB delete transport error: %s", exc)
            raise

        if response.status_code in (401, 403):
            raise ConfigEntryAuthFailed("InfluxDB rejected the token") from None
        if response.status_code >= 400:
            _LOGGER.warning(
                "InfluxDB delete failed (%s): %s",
                response.status_code,
                response.text[:500],
            )
            response.raise_for_status()
        _LOGGER.debug(
            "Deleted InfluxDB points for %s / %s in %s..%s",
            usage_point,
            reading_type.name,
            replace_window[0],
            replace_window[1],
        )


def _window_to_datetimes(window: tuple[date, date]) -> tuple[datetime, datetime]:
    start, stop = window
    return (
        datetime.combine(start, time.min, tzinfo=dt_util.UTC),
        datetime.combine(stop, time.min, tzinfo=dt_util.UTC),
    )


def _escape_predicate_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _escape_tag(value: str) -> str:
    """InfluxDB line protocol: spaces, commas, equals signs must be escaped in tags."""
    return value.replace(",", r"\,").replace(" ", r"\ ").replace("=", r"\=")
