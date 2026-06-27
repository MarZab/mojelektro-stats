# Testing rules

Developer tooling for verifying the HACS integration and its vendored API client. CI runs these tests; they are not part of the HACS install.

## Layout

```
tests/
├── lib/                       # mojelektro_api lib + CLI tests
│   ├── cassettes/             # VCR cassettes (committed, PII-scrubbed)
│   │   └── README.md          # recording procedure
│   └── conftest.py            # fixtures + scrubbing rules
└── ha/                        # Home Assistant integration tests (M4+)
    └── conftest.py
```

`pytest` from the repo root picks up both. Use markers when needed: `pytest -m "not ha"`, `pytest -m ha`.

## Lib testing

Tools: `pytest`, `pytest-asyncio` (auto mode), `pytest-recording` (VCR), `respx` for unit-level httpx mocks.

Patterns:

- **Happy paths** drive a real call through `MojElektroClient` against the production API. Captured as a VCR cassette on first run; replayed in CI. Cassettes are scrubbed at record time — see [`tests/lib/cassettes/README.md`](../../tests/lib/cassettes/README.md) for the rules and the three-identifier model.
- **Error mapping** does NOT use cassettes. Use `respx` to stub specific HTTP responses (one test per status code). Asserts the exception class and `__cause__` for `TransportError`.
- **Models** are `TypedDict`s — runtime-equivalent to `dict`. No `.from_dict()` round-trip tests; just assert the client returns parsed JSON in the expected shape.
- **CLI tests** use Typer's `CliRunner`. `--format json` output is deterministic and asserted directly; `table` format is smoke-tested (substring matches, no snapshot — terminal-sensitive).

The `mojelektro_token` / `mojelektro_identifikator` / `mojelektro_gsrn_mm` / `mojelektro_gsrn_mt` fixtures return the corresponding env var when set (re-record mode) or fake substitutes that match the cassettes (replay mode).

## CLI exit-code tests

Each `MojElektroError` subclass has a stable exit code (see `cli.md`). The exit-code test suite uses `respx` to stub a known endpoint (`/merilno-mesto/abc`) with each status and asserts the `CliRunner` exit code + the class name on stderr.

## HA testing (M4+)

Tools: `pytest-homeassistant-custom-component`. Supplies `hass` fixture, `MockConfigEntry`, recorder harness, integration loader.

Patterns:

- **ConfigFlow** — every step happy path; every error path.
- **OptionsFlow** — add/remove/change measurement routing.
- **Coordinator** — mock `MojElektroClient`; assert window math, per-point isolation, `last_synced_end` advancement.
- **Dispatcher** — pure unit; feed `(readings, config)`, assert sinks called with expected payloads.
- **Sinks** — `StatisticsSink` via recorder harness (idempotence on double import); `InfluxDBSink` via `respx`.

## Coverage

Lib + CLI: target ≥90%. HA integration: target ≥85%. Configured under `[tool.coverage.report]` once enforcement is enabled — don't lower the floor to make a test pass.

## Test hygiene

- Test names describe behavior, not the function under test.
- No `time.sleep`. Use `freezegun` for time-dependent code.
- No live network in CI. Lib uses cassettes; HA uses mocks. Live calls are for re-recording only.
- Treat flaky tests as broken tests — fix or delete; never `@pytest.mark.flaky`.

## When in doubt

Write the failing test first. If you cannot write a failing test for the change you want to make, the change is probably untestable as designed.
