# BUGLOG — bugs and data traps

Each entry: what, evidence (command/log), impact, handling.

## Step 1 — audit + join

### Kaggle description vs actual files
The description used for comparison is the one quoted in the exam brief; I did not re-read the Kaggle page itself.

| # | Kaggle says | Actually | Evidence | Handling |
|---|---|---|---|---|
| B2a | log file `dataset11-30week.csv` | `dataset11-30.csv` | `ls data` | `load.LOG_FILE` |
| B2b | schedules `export_arh_10-19`, `_20-30`, `_31-42` | `export_arh_11-20-final.csv`, `export_arh_21-30-final.csv`, `export_arh_31-42-final.csv` | `ls data` | `load.SCHED_FILES` |
| B2c | first schedule covers weeks 10–19, second 20–30 | the content is ISO weeks **11–20** and **21–30**: 11-20 holds 86 rows in ISO wk 10 (Sun 2020-03-08 23:00) and 2,431 in wk 21 (Mon 2020-05-18 00:00–12:00); 21-30 starts Mon 2020-05-18 | logs/audit.log | named by actual content; the "10-19 / 20-30" names are wrong (off by one, and 20-30 would overlap 31-42 in name only) |
| B2d | log column `end_time` | `stop_time` | header of dataset11-30.csv | kept as `stop_time` |
| B2e | log duration column (brief calls it `duraton`) | the column really is misspelled `duraton` | header | renamed to `duration` in `load.load_log` |
| B2f | schedule `duration` unit not stated | seconds: all values are multiples of 60, and duration == seconds to the next airing on the channel for 99.96% / 99.9995% / 99.9991% of rows | logs/audit.log | used as seconds |

### Environment
- **B1** `pandas` is not installed for `/usr/bin/python3` (numpy/scipy/implicit are, in the user site). → `.venv` with `--system-site-packages` + pandas 2.2.3 (DESIGN D1).

### Parsing traps
- **B4** `user_id` has up to 20 digits, max 18443832178892490378 > int64 max; 2,918,899 log rows would overflow. → uint64.
- **B5** Timestamp formats differ: log is `YYYY-MM-DD HH:MM:SS`, schedules are `DD.MM.YYYY HH:MM:SS`. Day-first inference could silently swap day and month for days ≤ 12. → explicit `format=`. Neither file has a timezone suffix.

### Clock / timezone
- **B6** Both log and schedule use **local wall-clock time (Europe/Kyiv)** and are on the same clock (no offset). Evidence (logs/extra_checks.log, logs/audit.log):
  - log: all 117 rows where `duraton != stop−start` (diff exactly −3600) span 2020-03-29 03:00, and these are the only 117 rows that span it; 0 views start in the non-existent hour 03:00–04:00.
  - schedule 11-20: all 257 airings spanning that instant have gap-to-next = duration + 3600; 0 airings start in the skipped hour.
  - alignment: view starts landing within 60 s after an airing start on the same channel peak at shift 0/+1 min (0.0193/0.0196), against 0.0164–0.0180 at ±1…3 h and 0.0169 median. Shift 0 beats every whole-hour shift both before DST (0.0200 vs ≤ 0.0179) and after (0.0192 vs ≤ 0.0181). The signal is modest (~15–20% lift), but it is consistent across both tests and both DST halves.
  - **Impact:** `duration` is real elapsed seconds while start times are wall clock. For the 257 airings spanning the 03-29 switch, start+duration ends 1 h early in wall time, so views of their last real hour (04:00–05:00 wall) are not joined to them; for the 117 log views spanning it, the wall interval is 1 h longer than `duraton`. **Not fixed** (one night, bounded). The fix would be to localise both files to Europe/Kyiv → UTC before joining.

### Log content
- **B7a** 17 exact duplicate log rows. → dropped before the join (D10).
- **B7b** 71,284 views overlap an earlier view by the same user on the **same channel** (2,617 users), and 379,398 (6.5%) overlap the same user's previous view on any channel. Likely several devices per account. Impact: summed screen time exceeds 1 for 24,005 interactions (max 31.13), and 4,217 interactions reach ≥ 0.8 only under sum, not union. Kept as sum per spec (D11, open).
- **B7c** 52 views longer than 24 h (max 342,145 s ≈ 95 h); min view length is 61 s (sub-minute views look pre-filtered). Kept: a long view only adds overlap to the airings it covers.
- **B7d** **Collection gap in weeks 20–27**: rows/week fall from ~410k to 105k and active users from ~4,650 to 2,406 (wk 26), then recover in wk 27–28 (4,275 / 4,620). Only 14 users appear just in wk 28–30, so this is not new users arriving. Test users per week: 1,232 → 795 (wk 26) → 1,226. **Impact:** labels built from period 21–30 (the natural validation target) come mostly from weeks 21–27 with thin data and from 28–30 at normal volume, which may not resemble the hidden 31–42 target.

### Schedule content
- **B8** The schedule files are **cut per channel at that channel's broadcast-day start**, not at Monday 00:00 (most channels at 06:00; others at 00:00/05:00/07:00/08:00). So each file runs into Monday until 12:00 of the next period, but the next file starts exactly where it ends: per-channel last end of 11-20 == first start of 21-30 for 398/399 shared channels, and 402/403 for 21-30 → 31-42. 0 shared (channel, start) keys. Exceptions: ch 487 overlaps 40 min (11-20 ends 01:00, 21-30 starts 00:20 on 05-18); ch 1528 has a 30-min gap on 07-27. → plain concat; period = source file (D5, D6).
- **B9** Within files: 1 duplicate (channel,start) and 1 `duration == 0` row (11-20, unlabelled); 2/2/8 overlapping consecutive airings (4 of them labelled-on-labelled, in 31-42); 396/3/4 gaps. 3 channel_ids have more than one channel_title in each file. → the zero-duration airing is excluded from the join (D9); the rest are left as is.
- **B10** **Schedule coverage gaps:** 5 log channels (149, 1174, 1508, 1509, 1510; 113,579 views) appear in no schedule, and 5 premium movie channels only get a schedule mid-way: 1516 TV1000 from 04-06, 1519 ViP Comedy / 1520 ViP Megahit / 1521 TV1000 Action from 04-27, 1528 ViP Premiere from 06-01. All of their unmatched views (291,994) fall before the channel's first airing. Overall 413,388 deduplicated views (7.1%) hit no airing, and 94.07% of viewed seconds are covered by some airing. **Impact:** movie-channel interest in weeks 11–17 is invisible; those channels are fully scheduled in 31–42.
- **B11** Labelled airings are a small minority: `tv_show_id != 0` is 10.76% / 11.31% / 11.18% of rows and 15.97% / 16.90% / 16.67% of airtime (11-20 / 21-30 / 31-42).

### Ranking-target trap (for later steps)
- **B12** The Kaggle answer is "strictly 5, desc by count", but counts are small integers: **750 of the 1,150** test users with ≥ 5 programmes in 21-30 have a tie between the 5th and 6th place. The Kaggle tie-break is unknown, so any offline validation target built from 21-30 is ambiguous for most users.
