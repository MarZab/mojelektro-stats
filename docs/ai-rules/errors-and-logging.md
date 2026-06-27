# Errors and logging

## Exception hierarchy

```
MojElektroError                       # base
├── AuthError                         # 401, 403
├── NotFoundError                     # 404
├── InvalidRequestError               # 400
└── TransportError                    # network / timeout
```

All raised by lib code with `raise ... from original` so the cause chain is preserved.

`MojElektroError` also serves as the catch-all for unexpected statuses (e.g. 5xx), with the HTTP status code accessible via `error.status_code`.

`TransportError(original=...)` retains the underlying `httpx` exception on `error.original`.

## Translation table

| HTTP / source        | Exception              |
|----------------------|------------------------|
| 400                  | `InvalidRequestError`  |
| 401                  | `AuthError`            |
| 403                  | `AuthError` (different message) |
| 404                  | `NotFoundError`        |
| 5xx                  | `MojElektroError(status_code=...)` |
| `httpx.ConnectError` | `TransportError`       |
| `httpx.ReadTimeout`  | `TransportError`       |
| `httpx.WriteTimeout` | `TransportError`       |
| `httpx.PoolTimeout`  | `TransportError`       |
| `httpx.RemoteProtocolError` | `TransportError` |

Translation happens at the response boundary inside the client. Nothing httpx-specific leaks out of the lib.

## HA-side translation

| Lib exception        | HA outcome                                        |
|----------------------|---------------------------------------------------|
| `AuthError`          | `ConfigEntryAuthFailed` from coordinator; `errors={"base": "invalid_auth"}` in ConfigFlow |
| `NotFoundError` (usage point) | Log WARNING, skip that point, do not raise |
| `InvalidRequestError` | Log ERROR, surface in diagnostics; ConfigFlow shows `errors={"base": "invalid_input"}` |
| `TransportError`     | `UpdateFailed` from coordinator; `errors={"base": "cannot_connect"}` in ConfigFlow |
| `MojElektroError` (other 5xx) | `UpdateFailed` |

InfluxDB sink:
- 401/403 → `ConfigEntryAuthFailed` for InfluxDB credentials (distinct user-facing message from the Moj Elektro token).
- Other 4xx → log full body once at WARNING, repeats at DEBUG.
- Transport-level → treated as transient; surface as `UpdateFailed`.

## Logging

### Loggers

- Lib: `logging.getLogger("mojelektro_api")`.
- Integration: `logging.getLogger("custom_components.mojelektro_stats")`.

### Levels

- `ERROR` — the user must act. ConfigFlow can't proceed; reauth needed; credentials wrong; misconfiguration that the integration can't recover from. One per cause; don't spam.
- `WARNING` — transient failure that the next cycle should resolve. One per occurrence; not one per usage point if all fail together.
- `INFO` — successful sync cycle. One line per cycle: `"synced N usage points, M readings written"`.
- `DEBUG` — request URLs, params (NOT headers), response sizes, dispatch decisions, sink batch sizes.

### Hard rules

- The API token must never appear in any log line, at any level. Tests verify this for the diagnostics dump.
- The InfluxDB token must never appear in any log line.
- Don't log full request/response bodies at INFO or above.
- Don't log stack traces at INFO. `logger.exception(...)` is for ERROR-level failures only.

## Retries

No retries inside the lib. No retries in the CLI. The HA coordinator's next interval is the retry — and it advances `last_synced_end` only on success, so retried windows pick up where they left off.

If you find yourself reaching for `tenacity` or a manual retry loop, stop. Almost certainly the right answer is to surface the error and let the higher layer decide.
