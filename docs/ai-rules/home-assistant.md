# Home Assistant integration rules

Primary codebase: `custom_components/mojelektro/`. This is what HACS installs. The vendored API client lives in `lib/mojelektro/`; integration logic (ConfigFlow, coordinator, sinks) lives alongside it.

## Manifest

`custom_components/mojelektro/manifest.json` essentials:

- `domain`: `mojelektro` (matches the lib name; do not change).
- `config_flow`: `true` — there is no YAML configuration path.
- `requirements`: `[]` — the API client is vendored under `lib/mojelektro/`; no PyPI dependency.
- `iot_class`: `cloud_polling`.
- `integration_type`: `service`.
- `version`: bumped in lockstep with the lib by `scripts/bump-version.sh`.

Don't add new `requirements` entries casually — every entry is installed into every user's HA. Prefer vendoring small pure-Python deps inside the integration if truly needed.

## ConfigFlow

Steps:
1. `user` — API token + server. Validate the token with a cheap request (e.g. `get_merilno_mesto` on the user-supplied identifier from step 2, or a probe of any known endpoint). The lib no longer exposes `/reading-type` at runtime; use it as a cheap GET if you must validate before asking for a meter.
2. `add_usage_point` — short identifikator or 18-digit GSRN. Validate via `get_merilno_mesto`.
3. `configure_measurements` — per reading type (from the hardcoded `KNOWN_READING_TYPES` catalog): `skip` / `sensor` / `sensor+backfill` / `influxdb`.
4. `add_another` — loop back to step 2 or finish.
5. `influxdb_config` (shown only if any measurement targets InfluxDB) — URL, org, bucket, token. Submitted credentials are validated with a Flux query against the bucket; failures surface as form errors (`invalid_influx_auth`, `cannot_connect_influx`). On success the finish dialog reports how many existing `mojelektro` points were found in the bucket.

OptionsFlow mirrors steps 2–5. Re-running with no changes is a no-op.

Use HA's standard error keys (`invalid_auth`, `cannot_connect`, `unknown`, etc.) where they apply. Custom keys for domain-specific issues (e.g. `unknown_meter`).

## Coordinator

- One `MojElektroDataUpdateCoordinator` per config entry.
- Update interval = 24h. First refresh of each day is scheduled at the user-configured local time using `async_track_time_change`.
- `_async_update_data`:
  - Per-usage-point window `[last_synced_end, now − 4h)`.
  - `asyncio.gather` over usage points; each wrapped in `asyncio.timeout(60)`.
  - Pass readings to the Dispatcher.
  - Advance per-point `last_synced_end` **only** if all sinks for that point succeed.
- Return only the minimum payload needed by sensor entities (latest value per measurement).

Error translation:
- `AuthError` → `ConfigEntryAuthFailed` (triggers reauth).
- `TransportError` → `UpdateFailed`.
- `NotFoundError` on a single usage point → log WARNING, skip that point this cycle, do **not** raise.
- Sink failure → log, do not advance the affected point's `last_synced_end`, raise `UpdateFailed`.

## Dispatcher

Pure routing. No I/O. Takes `(readings, per_measurement_config)`, calls the right sink for each reading. Easy to unit-test with mocked sinks.

## Sinks

Each sink is a class implementing a common `async def write(...)` interface, owning its own batching:

- `SensorSink` — no-op write; the coordinator's latest payload is the source for entity state. Sensor entities pull during `_handle_coordinator_update`.
- `StatisticsSink` — batches by `(usage_point, reading_type_id)`, calls `homeassistant.components.recorder.statistics.async_import_statistics` once per batch. `statistic_id` shape: `mojelektro:<usage_point>_<reading_type_id>`.
- `InfluxDBSink` — one async httpx client per config entry, batched line-protocol POST to `/api/v2/write?org=...&bucket=...&precision=s`. Token from OptionsFlow.

Sinks raise on hard failures. The dispatcher catches per-point and signals back to the coordinator.

## Migrations

Per-measurement routing schema in the config entry's `data` carries a `version`. Adding new sink types, new routing fields, or changing key names requires bumping the version and adding a step to `async_migrate_entry`. Tests cover each step.

## Diagnostics

`diagnostics.py` implements `async_get_config_entry_diagnostics`. Output:
- Redacted config (token replaced with `**REDACTED**`, InfluxDB token also redacted).
- Recent sync results (last 5 cycles): timestamps, per-point counts, per-point errors.
- Library version, integration version, HA version.

Tests verify redaction.

## Sensor platform

- Devices: one device per usage point. Identifier `(DOMAIN, usage_point)`.
- Entities:
  - One measurement sensor per reading type with `sensor` or `sensor+backfill` routing. `state_class` set per measurement semantics (`measurement` for instantaneous, `total_increasing` for cumulative). `device_class` set where it maps cleanly.
  - Diagnostic sensors per entry: `last_sync_at`, `last_sync_status`, `last_error`.
- Unique IDs: `(entry_id, usage_point, reading_type_id, "value")` for measurement sensors; `(entry_id, "<diag-name>")` for diagnostics.
- Stable across reconfigurations — never include user-facing names in the unique ID.

## Things to avoid

- Calling the lib from inside an entity's `update` method. The coordinator owns I/O.
- Logging the API token at any level.
- Synchronous I/O anywhere in HA code.
- Hard-coded entity names in tests — they will break when translations change.
