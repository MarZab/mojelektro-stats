from __future__ import annotations

from typing import Final

DOMAIN: Final = "mojelektro"
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
CONF_INFLUXDB: Final = "influxdb"
CONF_INFLUXDB_URL: Final = "url"
CONF_INFLUXDB_ORG: Final = "org"
CONF_INFLUXDB_BUCKET: Final = "bucket"
CONF_INFLUXDB_TOKEN: Final = "token"

SERVER_PROD: Final = "prod"
SERVER_TEST: Final = "test"

# Routing values are now sets of sink names. Each reading type independently
# chooses any combination of:
SINK_STATISTICS: Final = "statistics"
SINK_INFLUXDB: Final = "influxdb"
SINK_OPTIONS: Final = (SINK_STATISTICS, SINK_INFLUXDB)

DEFAULT_BACKFILL_DAYS: Final = 7
SYNC_CUTOFF_HOURS: Final = 4
# The Moj Elektro API caps a single /meter-readings request at a 35-day
# window. The coordinator chunks larger windows into successive requests.
MAX_FETCH_WINDOW_DAYS: Final = 35
# Bump on every breaking change to the entry data shape; bumps require an
# `async_migrate_entry` step. v2 switched routing values from a single string
# (skip / sensor / sensor+backfill / influxdb) to a list of sink names
# (statistics, influxdb).
DATA_CONFIG_VERSION: Final = 2
STATISTIC_ID_PREFIX: Final = "mojelektro"
