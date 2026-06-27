#!/usr/bin/env python3
"""Record the /reading-type catalog cassette outside the pytest harness.

pytest-homeassistant-custom-component disables DNS globally when its plugin
loads, which blocks live HTTP recording. This script bypasses pytest and
writes the cassette directly via vcrpy + httpx, using the same scrubbing
rules as `tests/lib/conftest.py`.

Usage:
    set -a; source .env; set +a   # MOJELEKTRO_APIKEY
    uv run scripts/record-reading-types.py

Then verify scrubbing and regenerate the typed catalog:
    grep -RI "$MOJELEKTRO_APIKEY" tests/lib/cassettes/ && echo LEAK || echo clean
    make regen-reading-types
"""

from __future__ import annotations

import os
import pathlib
import sys

import httpx
import vcr

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tests" / "lib"))
from conftest import _scrub_request, _scrub_response  # noqa: E402

CASSETTE = (
    REPO_ROOT
    / "tests"
    / "lib"
    / "cassettes"
    / "test_client_recorded"
    / "test_recorded_reading_types.yaml"
)


def main() -> int:
    token = os.environ.get("MOJELEKTRO_APIKEY")
    if not token:
        sys.stderr.write("MOJELEKTRO_APIKEY not set\n")
        return 1

    CASSETTE.parent.mkdir(parents=True, exist_ok=True)
    CASSETTE.unlink(missing_ok=True)

    my_vcr = vcr.VCR(
        filter_headers=[
            ("x-api-token", "REDACTED"),
            ("X-API-TOKEN", "REDACTED"),
            ("authorization", "REDACTED"),
            ("Set-Cookie", None),
            ("set-cookie", None),
            ("Cookie", None),
            ("cookie", None),
        ],
        before_record_request=_scrub_request,
        before_record_response=_scrub_response,
        decode_compressed_response=True,
        record_mode="once",
    )

    with my_vcr.use_cassette(str(CASSETTE)):
        response = httpx.get(
            "https://api.informatika.si/mojelektro/v1/reading-type",
            headers={"X-API-TOKEN": token, "Accept": "application/json"},
            timeout=30.0,
        )
        response.raise_for_status()
        body = response.json()
        print(f"recorded {len(body)} reading types to {CASSETTE.relative_to(REPO_ROOT)}")
        # Sanity check: at least one entry should now have a non-REDACTED naziv
        sample_naziv = body[0].get("naziv", "")
        print(f"sample naziv (post-API): {sample_naziv!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
