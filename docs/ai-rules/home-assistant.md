# Home Assistant integration rules

Primary codebase: `custom_components/mojelektro_stats/`. This is what HACS installs. The vendored API client lives in `lib/mojelektro_api/`; integration logic (ConfigFlow, coordinator, sinks) lives alongside it.

## Manifest

`custom_components/mojelektro_stats/manifest.json` essentials:

- `domain`: `mojelektro_stats` (must match the integration directory name; do not change).
- `config_flow`: `true` — there is no YAML configuration path.
- `requirements`: `[]` — the API client is vendored under `lib/mojelektro_api/`; no PyPI dependency.
- `iot_class`: `cloud_polling`.
- `integration_type`: `service`.
- `version`: bumped in lockstep with the lib's `__about__.py` (by hand).

Don't add new `requirements` entries casually — every entry is installed into every user's HA. Prefer vendoring small pure-Python deps inside the integration if truly needed.

## ConfigFlow

Steps:
1. `user` — API token + server. Validate the token with a cheap request (e.g. `get_merilno_mesto` on the user-supplied identifier from step 2, or a probe of any known endpoint). The lib no longer exposes `/reading-type` at runtime; use it as a cheap GET if you must validate before asking for a meter.
2. `add_usage_point` — short identifikator or 18-digit GSRN. Validate via `get_merilno_mesto`.
3. `configure_measurements` — per reading type (from the hardcoded `KNOWN_READING_TYPES` catalog): a list of target sinks, any combination of `statistics` and `influxdb`. Empty list means the reading type is not written anywhere.
4. `influxdb_config` (run only if a measurement targets InfluxDB and credentials aren't captured yet) — URL, org, bucket, token. Submitted credentials are validated with a Flux query against the bucket; failures surface as form errors (`invalid_influx_auth`, `cannot_connect_influx`). On success the finish dialog reports how many existing `mojelektro` points were found in the bucket.

OptionsFlow opens a menu (`async_step_init`): `edit_measurements` (re-runs `configure_measurements` on the existing point), `backfill`, and `influxdb_config` (only when routing uses InfluxDB). Re-running with no changes is a no-op.

Use HA's standard error keys (`invalid_auth`, `cannot_connect`, `unknown`, etc.) where they apply. Custom keys for domain-specific issues (e.g. `unknown_meter`).

## Coordinator

- One `MojElektroDataUpdateCoordinator` per config entry.
- Update interval = 24h. First refresh of each day is scheduled at the user-configured local time using `async_track_time_change`.
- `_async_update_data`:
  - Per-usage-point window `[last_synced_end, now − 4h)`.
  - `asyncio.gather` over usage points; each wrapped in `asyncio.timeout(60)`.
  - Pass readings to the Dispatcher.
  - Advance per-point `last_synced_end` **only** if all sinks for that point succeed.
- There are no HA entity platforms (`PLATFORMS = []`); data flows directly to the sinks. `_async_update_data` returns nothing.

Error translation:
- `AuthError` → `ConfigEntryAuthFailed` (triggers reauth).
- `TransportError` → `UpdateFailed`.
- `NotFoundError` on a single usage point → log WARNING, skip that point this cycle, do **not** raise.
- Sink failure → log, do not advance the affected point's `last_synced_end`, raise `UpdateFailed`.

## Dispatcher

Pure routing. No I/O. Takes `(readings, per_measurement_config)`, calls the right sink for each reading. Easy to unit-test with mocked sinks.

## Sinks

Each sink is a class implementing a common `async def write(...)` interface, owning its own batching:

- `StatisticsSink` — batches by `(usage_point, reading_type_id)`, calls `homeassistant.components.recorder.statistics.async_import_statistics` once per batch. `statistic_id` shape: `mojelektro_stats:<usage_point>_<reading_type_id>`.
  - **STANJE (daily cumulative register) timing:** the API stamps each daily reading at the midnight *after* the day it closes. The sink places each row at the Europe/Ljubljana midnight that starts the day it closes (local date of `timestamp - 1 s`), which matches the mojelektro.si portal and the CLI's `daily` command. A fixed 24 h shift would be wrong on the 23-hour spring DST day. The value is written straight through as `sum`, with no accumulation.
  - **STANJE anchor row:** if the statistic has no earlier row in the recorder and nothing is cached in `_tail`, the sink writes one extra row one local day before the first reading, with the same value. Without it, HA's `change` for day one would be the whole lifetime register total.
  - **Data imported before 1.0.1** sits one day late. Running a backfill from the options flow re-imports the range with `replace_window`, which deletes the old rows first and fixes them.
- `InfluxDBSink` — one async httpx client per config entry, batched line-protocol POST to `/api/v2/write?org=...&bucket=...&precision=s`. Token from OptionsFlow.

Sinks raise on hard failures. The dispatcher catches per-point and signals back to the coordinator.

## Things to avoid

- Calling the lib from inside HA's update path. The coordinator owns I/O.
- Logging the API token at any level.
- Synchronous I/O anywhere in HA code.
