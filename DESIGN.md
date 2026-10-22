# DESIGN — decisions

## Step 1 — audit + join

| # | Decision | Why | Alternatives / open |
|---|---|---|---|
| D1 | Python env = `.venv` created with `--system-site-packages` on `/usr/bin/python3` 3.9.6; adds pinned `pandas==2.2.3`, `pyarrow==17.0.0`; reuses numpy 2.0.2, scipy 1.13.1, implicit 0.7.3 | pandas was not installed (B1); a project venv leaves the global setup untouched | — |
| D2 | Seed 42 for every RNG (`np.random.default_rng(42)`) | exam rule | — |
| D3 | All CSVs are read as `str` first, then cast explicitly: `user_id`→uint64, timestamps with explicit `format=` (log `%Y-%m-%d %H:%M:%S`, schedule `%d.%m.%Y %H:%M:%S`) | avoids int64 overflow (B4) and day/month swapping (B5) | — |
| D4 | Parsed files are cached in `artifacts/*.parquet` (gitignored), derived from `data/` only | speed; reproducible from raw | — |
| D5 | Schedules = plain concatenation of the 3 files; no dedup across files | measured: per-channel the files tile exactly (B8) and share 0 (channel,start) keys | — |
| D6 | Period of an interaction = **source file of the airing** (11-20 / 21-30 / 31-42), not calendar week of the view | files are cut at each channel's broadcast-day boundary, not at Monday 00:00 (B8); an airing belongs to exactly one file | calendar ISO week of airing start; differs only for Monday 00:00–12:00 airings |
| D7 | Clocks: log and schedule used as-is, **no timezone shift** | alignment test (src/audit.py) peaks at shift 0 before and after DST; see RESULTS | — |
| D8 | Join: view ↔ airing when `vsetv_id == channel_id` and `min(stops) − max(starts) > 0`; per-channel searchsorted with key `channel·1e11 + epoch_s`; lower bound uses running max of airing ends (correct with overlapping airings) | no cartesian merge; verified identical to brute-force merge on a 10-channel sample (24,525 pairs) | — |
| D9 | Airings with `duration == 0` are excluded from the join | screen time undefined (1 row, unlabelled) | — |
| D10 | 17 exact duplicate log rows dropped before join | identical rows would double-count overlap | keep them (effect ≤ 17 views) |
| D11 | Screen time = **sum** of the overlaps of all the user's views with that airing / airing duration, not clipped | as specified in the task | **open:** union of intervals. Sum > union for 42,087 rows because the same user has overlapping views on one channel (multi-device?); 4,217 rows cross 0.8 only under sum. Kaggle's exact rule is unknown, so revisit when validating against the leaderboard |
| D12 | Unlabelled airtime (`tv_show_id == 0`) kept only as `artifacts/unlab_seconds.parquet`: seconds per (user, channel, period) | not an item, but a possible feature | — |
| D13 | The positive threshold `screen_time >= 0.8` is inclusive | matches "≥ 0.8" in the competition description | — |
