from __future__ import annotations

from typing import Final

DOMAIN: Final = "mojelektro_stats"
# No HA entity platforms — data flows directly to long-term statistics and/or
# InfluxDB. Sensor entities were dropped: their state-change history can't be
# backdated, which made them misleading for delayed meter data.
PLATFORMS: Final[list[str]] = []

CONF_TOKEN: Final = "api_token"
CONF_SERVER: Final = "server"
CONF_USAGE_POINTS: Final = "usage_points"
CONF_ROUTING: Final = "routing"
CONF_IDENTIFIKATOR: Final = "identifikator"
CONF_NAZIV: Final = "naziv"
CONF_BACKFILL_DAYS: Final = "backfill_days"
CONF_BACKFILL_FROM: Final = "backfill_from"
CONF_SYNC_ENABLED: Final = "sync_enabled"
CONF_SYNC_TIME: Final = "sync_time"
CONF_INFLUXDB: Final = "influxdb"
CONF_INFLUXDB_URL: Final = "url"
CONF_INFLUXDB_ORG: Final = "org"
CONF_INFLUXDB_BUCKET: Final = "bucket"
CONF_INFLUXDB_TOKEN: Final = "token"

SERVER_PROD: Final = "prod"
SERVER_TEST: Final = "test"

# Routing values are lists of sink names. Each reading type independently
# chooses any combination of:
SINK_STATISTICS: Final = "statistics"
SINK_INFLUXDB: Final = "influxdb"
SINK_OPTIONS: Final = (SINK_STATISTICS, SINK_INFLUXDB)

DEFAULT_BACKFILL_DAYS: Final = 7
# Daily sync runs by default at this local time ("HH:MM:SS"); configurable
# per entry, and can be turned off entirely.
DEFAULT_SYNC_ENABLED: Final = True
DEFAULT_SYNC_TIME: Final = "06:00:00"
SYNC_CUTOFF_HOURS: Final = 4
# The Moj Elektro API caps a single /meter-readings request at a 35-day
# window. The coordinator chunks larger windows into successive requests.
MAX_FETCH_WINDOW_DAYS: Final = 35
STATISTIC_ID_PREFIX: Final = "mojelektro_stats"
