"""Lib-test fixtures + VCR scrubbing.

This API has THREE distinct identifiers per measuring point — they are NOT
interchangeable and the wrong one returns HTTP 400. See:
`docs/superpowers/specs/2026-06-07-mojelektro-design.md` and the
"api-identifier-model" memory entry.

| Identifier  | Endpoint                                  | Env var                    |
|-------------|-------------------------------------------|----------------------------|
| identifikator | GET /merilno-mesto/{identifikator}      | MOJELEKTRO_IDENTIFIKATOR   |
| gsrnMm      | GET /meter-readings?usagePoint={gsrnMm}   | MOJELEKTRO_GSRN_MM         |
| gsrnMt      | GET /merilna-tocka/{gsrnMt}               | MOJELEKTRO_GSRN_MT         |

Recording rules:

  - X-API-TOKEN header → REDACTED (vcrpy filter_headers).
  - All three real identifiers → distinct fake values in cassettes
    (request URLs AND response bodies).
  - PII fields (placnik, naslovnik, address, contact, supplier, …) →
    REDACTED in response bodies.
  - Replay is the default; pass `--record-mode=once` to re-record.

To re-record (production server; we have no test creds):

  export MOJELEKTRO_APIKEY="<your real token>"
  export MOJELEKTRO_IDENTIFIKATOR="<short id like 4-0000000>"
  export MOJELEKTRO_GSRN_MM="<18-digit gsrn of the meter>"
  export MOJELEKTRO_GSRN_MT="<18-digit gsrn of the measuring point>"
  rm -rf tests/lib/cassettes/
  uv run pytest tests/lib/test_client_recorded.py --record-mode=once -v

Verify scrubbing before committing:

  for v in "$MOJELEKTRO_APIKEY" "$MOJELEKTRO_IDENTIFIKATOR" \\
           "$MOJELEKTRO_GSRN_MM" "$MOJELEKTRO_GSRN_MT"; do
    grep -RI "$v" tests/lib/cassettes/ && echo "LEAK: $v" || echo "clean"
  done
"""

from __future__ import annotations

import copy
import json
import os
import re
from typing import Any

import pytest

# Plausible-looking but unreal substitutes. Distinct shapes match the real
# identifiers (short-form vs 18-digit GSRNs) so the substitution is visually
# obvious and consumers stay correct.
FAKE_IDENTIFIKATOR = "4-0000000"
FAKE_GSRN_MM = "100000000000000000"
FAKE_GSRN_MT = "200000000000000000"

_PII_STRING_KEYS = (
    "placnik",
    "naslovnik",
    "imeInPriimek",
    "ime",
    "priimek",
    "naslov",
    "ulica",
    "hisnaStevilka",
    "posta",
    "kraj",
    "davcnaStevilka",
    "davcnaSt",
    "emso",
    "telefon",
    "email",
    "dobavitelj",
    # Meter / grid identifiers
    "tovarniskaStevilkaMkn",
    "statisticnaPopulacija",
    # Contract number (also appears here as a hyphen-suffixed string variant
    # of the integer stevilkaSzP)
    "stPogodbeOUporabiSistema",
    # Substation / line topology — identifies physical address indirectly
    "nn",
    "sn",
    "tp",
    "rtp",
)

_PII_INT_KEYS = ("stevilkaSzP",)


def _id_substitutions() -> list[tuple[str, str]]:
    """Pairs of (real, fake) loaded from env vars, in long→short order so
    longer values are replaced before shorter ones they might contain."""
    pairs = [
        ("MOJELEKTRO_GSRN_MM", FAKE_GSRN_MM),
        ("MOJELEKTRO_GSRN_MT", FAKE_GSRN_MT),
        ("MOJELEKTRO_IDENTIFIKATOR", FAKE_IDENTIFIKATOR),
    ]
    return [(os.environ[var], fake) for var, fake in pairs if os.environ.get(var)]


@pytest.fixture
def mojelektro_token() -> str:
    return os.environ.get("MOJELEKTRO_APIKEY", "REDACTED")


@pytest.fixture
def mojelektro_identifikator() -> str:
    return os.environ.get("MOJELEKTRO_IDENTIFIKATOR", FAKE_IDENTIFIKATOR)


@pytest.fixture
def mojelektro_gsrn_mm() -> str:
    return os.environ.get("MOJELEKTRO_GSRN_MM", FAKE_GSRN_MM)


@pytest.fixture
def mojelektro_gsrn_mt() -> str:
    return os.environ.get("MOJELEKTRO_GSRN_MT", FAKE_GSRN_MT)


def _scrub_request(request: Any) -> Any:
    subs = _id_substitutions()
    if not any(real in request.uri for real, _ in subs):
        return request
    # Important: do not mutate the original — vcrpy may pass the same
    # object that's about to go on the wire, and we don't want the scrubbed
    # value sent to the real API.
    scrubbed = copy.copy(request)
    uri = request.uri
    for real, fake in subs:
        uri = uri.replace(real, fake)
    scrubbed.uri = uri
    return scrubbed


def _scrub_response(response: dict[str, Any]) -> dict[str, Any]:
    # Drop session cookies — filter_headers with value=None doesn't reliably
    # remove these for httpx-backed transports, so we do it directly here.
    headers = response.get("headers", {})
    for key in list(headers):
        if key.lower() in {"set-cookie", "cookie"}:
            del headers[key]

    body = response.get("body", {}).get("string")
    if body is None:
        return response
    text = body.decode("utf-8", errors="replace") if isinstance(body, bytes) else body

    for real, fake in _id_substitutions():
        text = text.replace(real, fake)

    for key in _PII_STRING_KEYS:
        text = re.sub(
            rf'"{key}"\s*:\s*"[^"]*"',
            f'"{key}": "REDACTED"',
            text,
        )
    for key in _PII_INT_KEYS:
        text = re.sub(
            rf'"{key}"\s*:\s*\d+',
            f'"{key}": 0',
            text,
        )

    # `naziv` is context-dependent: PII on /merilno-mesto (the owner's
    # address-like name) but a generic Slovene description on /reading-type
    # ("Prejeta 15 minutna delovna energija"). Parse the JSON and only redact
    # naziv when the enclosing object isn't a reading-type catalog item.
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if parsed is not None:
        _scrub_naziv(parsed)
        text = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))

    response["body"]["string"] = text.encode("utf-8")
    return response


def _scrub_naziv(obj: Any) -> None:
    """Walk a parsed JSON tree and replace `naziv` with REDACTED unless the
    enclosing object is a reading-type catalog item (identified by the
    presence of both `readingType` and `oznaka` keys)."""
    if isinstance(obj, dict):
        is_reading_type = "readingType" in obj and "oznaka" in obj
        for key, value in obj.items():
            if key == "naziv" and not is_reading_type and isinstance(value, str):
                obj[key] = "REDACTED"
            else:
                _scrub_naziv(value)
    elif isinstance(obj, list):
        for item in obj:
            _scrub_naziv(item)


@pytest.fixture
def vcr_config(record_mode: str) -> dict[str, Any]:
    # `record_mode` is provided by pytest-recording and reflects the
    # --record-mode CLI flag (default: "none" → replay only).
    return {
        "filter_headers": [
            ("x-api-token", "REDACTED"),
            ("X-API-TOKEN", "REDACTED"),
            ("authorization", "REDACTED"),
            # Strip session cookies entirely (drops the header from cassette)
            ("Set-Cookie", None),
            ("set-cookie", None),
            ("Cookie", None),
            ("cookie", None),
        ],
        "before_record_request": _scrub_request,
        "before_record_response": _scrub_response,
        "decode_compressed_response": True,
        "record_mode": record_mode,
    }
