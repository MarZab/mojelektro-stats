from __future__ import annotations

import pytest

from custom_components.mojelektro_stats._naming import slug_reading_type
from mojelektro_api import KNOWN_READING_TYPES


@pytest.mark.ha
def test_reading_type_slugs_are_unique() -> None:
    """Every reading type must map to a distinct statistic slug.

    The statistic_id is derived from this slug, so a collision would make two
    reading types share one statistic_id and silently overwrite each other —
    e.g. if the tariff suffix (T0/T1/T2) were ever dropped from the slug.
    """
    slugs = [slug_reading_type(rt).replace("-", "_") for rt in KNOWN_READING_TYPES]
    assert len(slugs) == len(set(slugs)), "duplicate statistic slugs: " + ", ".join(
        s for s in slugs if slugs.count(s) > 1
    )
