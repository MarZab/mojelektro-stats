# Changelog

All notable changes to the Moj Elektro Stats integration. Versions follow [SemVer](https://semver.org); pre-releases (`X.Y.ZbN`, `X.Y.ZrcN`) go to the HACS beta channel.

## 1.0.1

### Fixed

- **Daily register statistics were one day late.** The Moj Elektro API stamps each daily register reading (`A+`/`A-`/`R+`/`R-`, T0/T1/T2, "24 urno stanje") at the midnight *after* the day it closes. The integration stored each reading on that next day, so Home Assistant charts and the Energy dashboard showed every day's usage on the following day. For example, the 45.4 kWh used on Oct 24 appeared on Oct 25 in Home Assistant, unlike on the mojelektro.si portal. Each reading is now stored on the day it describes. ([#1](https://github.com/MarZab/mojelektro-stats/pull/1), thanks to amadejkastelic)
- **Day-one spike on a new meter.** The first imported day of a daily register statistic no longer shows the meter's whole lifetime total as that day's usage. A zero-change starting row is written one day before the first reading. ([#1](https://github.com/MarZab/mojelektro-stats/pull/1))
- **Spring daylight-saving day.** Days are worked out in Slovenian local time, so the 23-hour day when clocks go forward (late March) gets its own reading, rather than its usage being added to the day before.

Only Home Assistant statistics for the **daily register** reading types were affected. 15-minute readings and InfluxDB data were always stored at the API's own timestamps.

### Recommended after upgrading: re-import your history

Statistics imported before 1.0.1 stay on the wrong day until they're rewritten. After updating and restarting Home Assistant:

1. Go to **Settings → Devices & Services → Moj Elektro Stats → Configure**.
2. Choose **Backfill from a date** and pick the earliest date you imported (up to 2 years back).

The backfill deletes the existing statistics in each window before importing it again, so the old one-day-late rows are replaced rather than duplicated. It runs in the background and can take a few minutes for long histories. Afterwards, daily totals in Home Assistant should match the mojelektro.si portal.

### Changed

- **Requires Home Assistant 2026.11.0 or newer** (was 2025.4.0). HACS won't offer this update on older versions; update Home Assistant first.
- Prepared for the HACS default catalog / Home Assistant Marketplace: brand icon, LICENSE, `hacs.json` country, and `hassfest` + HACS validation in CI.
- Releases are now full GitHub Releases. Pre-release versions are published to the HACS beta channel for users who opt in.

### Developer tooling

Not shipped to Home Assistant users:

- `mise` replaces the Makefile (`mise tasks` lists everything). The CLI and scripts moved to `tools/`.
- The CLI reads `.env` and `MOJELEKTRO_USAGE_POINT`. New `daily` and `hourly` commands show per-day and per-hour usage and check them against the daily register.
- `mise run release` bumps the version files, commits, tags and pushes a release.

## 1.0.0

- First release: Moj Elektro readings imported into Home Assistant long-term statistics, optional InfluxDB v1/v2 output, backfill up to 2 years, multiple meters and accounts.
