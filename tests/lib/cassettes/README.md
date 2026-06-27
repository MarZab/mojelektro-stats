# Recorded VCR cassettes

Replay-only in CI. There is no public Moj Elektro test environment, so cassettes are recorded against **production** with PII scrubbed at record time. See `tests/lib/conftest.py` for the scrubbing rules.

## What gets scrubbed

- **`X-API-TOKEN` header** → `REDACTED`
- **The three real identifiers** (loaded from env vars below) → fake but well-formed substitutes in URLs and response bodies:
  - `MOJELEKTRO_IDENTIFIKATOR` → `4-0000001`
  - `MOJELEKTRO_GSRN_MM` → `100000000000000000`
  - `MOJELEKTRO_GSRN_MT` → `200000000000000000`
- **PII fields** in response bodies (`naziv`, address, contact, supplier, contract number, substation/line topology — full list in `_PII_STRING_KEYS` / `_PII_INT_KEYS`) → `"REDACTED"` or `0`
- **`Set-Cookie` / `Cookie`** headers → dropped entirely

The scrubber is regex-based. Eyeball the recorded YAML before committing.

## The three identifiers

The API exposes **three distinct identifiers per measuring point** — they are not interchangeable. Passing the wrong one returns HTTP 400 (`Vrednost 'X' je nepricakovana za 'GSRNMT'`).

| Identifier      | Endpoint                                    | Shape          |
|-----------------|---------------------------------------------|----------------|
| `identifikator` | `GET /merilno-mesto/{identifikator}`        | short form (e.g. `4-0000001`) |
| `gsrnMm`        | `GET /meter-readings?usagePoint={gsrnMm}`   | 18-digit       |
| `gsrnMt`        | `GET /merilna-tocka/{gsrnMt}`               | 18-digit       |

## Re-record

```bash
# 1. Export the four secrets
export MOJELEKTRO_APIKEY="<your real token>"
export MOJELEKTRO_IDENTIFIKATOR="<short id, e.g. 4-XXXXXXX>"
export MOJELEKTRO_GSRN_MM="<18-digit meter GSRN>"
export MOJELEKTRO_GSRN_MT="<18-digit measuring-point GSRN>"

# 2. Drop the existing cassettes and re-record against the live API
rm -rf tests/lib/cassettes/test_client_recorded/
uv run pytest tests/lib/test_client_recorded.py --record-mode=once -v

# 3. Verify the scrubber caught everything
for v in "$MOJELEKTRO_APIKEY" "$MOJELEKTRO_IDENTIFIKATOR" \
         "$MOJELEKTRO_GSRN_MM" "$MOJELEKTRO_GSRN_MT"; do
  grep -RIl "$v" tests/lib/cassettes/ && echo "LEAK: $v" || echo "clean"
done

# 4. Eyeball merilno-mesto and merilna-tocka cassettes for PII the regex
#    missed (real name variants, address fragments, contract numbers, ...)
less tests/lib/cassettes/test_client_recorded/test_recorded_merilno_mesto.yaml
less tests/lib/cassettes/test_client_recorded/test_recorded_merilna_tocka.yaml

# 5. Confirm replay works without any credentials
unset MOJELEKTRO_APIKEY MOJELEKTRO_IDENTIFIKATOR MOJELEKTRO_GSRN_MM MOJELEKTRO_GSRN_MT
uv run pytest tests/lib/test_client_recorded.py -v

# 6. Commit the cassettes
git add tests/lib/cassettes/
git commit -m "test(lib): refresh recorded VCR cassettes"
```

## If you spot leaked PII

1. Add the offending key name to `_PII_STRING_KEYS` (or `_PII_INT_KEYS`) in `tests/lib/conftest.py`.
2. Re-run the procedure from step 2.

## The reading-types cassette is also a data source

`test_recorded_reading_types.yaml` is consumed by `scripts/regen-reading-types.py` to refresh the hardcoded `custom_components/mojelektro_stats/lib/mojelektro_api/reading_types.py` catalog. If a new reading type is added upstream, re-record, then run `make regen-reading-types`.

## When to re-record

- Upstream API response shape changes.
- The hardcoded date window in `test_recorded_meter_readings_window` ages out.
- A new endpoint gets added to the library.
