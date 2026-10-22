# RESULTS

Every number has the command that produced it; full outputs are in `logs/`. All commands run from the repo root.
Pipeline: `src/load.py` (parsing + parquet cache) → `src/join.py` → `src/stats.py`; checks: `src/audit.py`, `src/check_join.py`, `src/extra_checks.py`.

## Step 1 — audit + join

### Weeks ↔ dates (`.venv/bin/python src/audit.py` → logs/audit.log)
The weeks are ISO weeks of 2020 and **line up**: log 2020-03-09 00:00:02 (Mon, wk 11) … 2020-07-26 23:59:58 (Sun, wk 30), 20 distinct weeks.

| file | first start | last start / max end | ISO weeks of start |
|---|---|---|---|
| dataset11-30.csv | 2020-03-09 00:00:02 Mon | 2020-07-26 23:58:42 / stop 23:59:58 Sun | 11..30 |
| export_arh_11-20 | 2020-03-08 23:00 Sun (86 rows in wk 10) | 2020-05-18 11:45 / 12:00 Mon (2,431 rows in wk 21) | 10..21 |
| export_arh_21-30 | 2020-05-18 00:00 Mon | 2020-07-27 11:55 / 12:00 Mon (2,429 rows in wk 31) | 21..31 |
| export_arh_31-42 | 2020-07-27 00:00 Mon | 2020-10-19 11:55 / 12:00 Mon (2,399 rows in wk 43) | 31..43 |

The spill-over past Sunday is the end of each channel's broadcast day (BUGLOG B8).

### Audit numbers (`src/audit.py` → logs/audit.log, `src/extra_checks.py` → logs/extra_checks.log)
| item | value |
|---|---|
| log rows / users / channels | 5,821,987 / 4,914 / 202 |
| log `duraton == stop−start` | 5,821,870; 117 differ by −3600 s, all spanning DST 2020-03-29 03:00 |
| log exact duplicate rows | 17 |
| log view length min / p50 / p99 / max (s) | 61 / 396 / 14,079 / 342,145 |
| log channels absent from schedules | 149, 1174, 1508, 1509, 1510 (113,579 rows) |
| schedule duration unit | seconds (all multiples of 60; = gap to next airing 99.9629% / 99.9995% / 99.9991%) |
| schedule rows 11-20 / 21-30 / 31-42 | 1,074,235 / 1,074,394 / 1,295,378 |
| share tv_show_id != 0, rows | 10.7624% / 11.3092% / 11.1762% |
| share tv_show_id != 0, airtime | 15.9663% / 16.9000% / 16.6721% |
| distinct labelled programmes | 5,847 / 6,363 / 6,636 |
| duplicate (channel,start) | 1 / 0 / 0 |
| duration == 0 | 1 / 0 / 0 |
| overlapping consecutive airings on a channel | 2 / 2 / 8 |
| gaps between airings on a channel | 396 / 3 / 4 |
| per-channel tiling 11-20→21-30, 21-30→31-42 | 398/399, 402/403 channels exact |
| clock: view-start-after-airing-start rate at shift 0 / +1 min / ±1 h / ±2 h / ±3 h / median | 0.0193 / 0.0196 / 0.0170, 0.0176 / 0.0167, 0.0179 / 0.0164, 0.0180 / 0.0169 |
| clock: view-stop-before-airing-end rate at 0 / +1 min / median | 0.0213 / 0.0256 / 0.0168 |
| same-user same-channel overlapping views | 71,284 (2,617 users) |

### Test users (`.venv/bin/python src/stats.py` → logs/stats.log)
| | count of 1260 |
|---|---|
| any view in 11-30 | 1,260 |
| a labelled view (overlap > 0 with a tv_show_id != 0 airing) | 1,258 |
| ≥ 1 airing at screen time ≥ 0.8, 11-30 | 1,256 |
| any joined view / labelled / ≥ 0.8 in 11-20 | 1,255 / 1,250 / 1,242 |
| any joined view / labelled / ≥ 0.8 in 21-30 | 1,246 / 1,246 / 1,238 |

### Join (`.venv/bin/python src/join.py` → logs/join.log; check `src/check_join.py` → logs/check_join.log)
| item | value |
|---|---|
| log rows after exact-dup drop | 5,821,970 |
| (view, airing) pairs with overlap > 0, any airing | 7,752,415 |
| views with ≥ 1 airing | 5,408,582 (unmatched: 413,388 = 7.10%) |
| share of viewed seconds covered by an airing | 94.0656% |
| interactions (user, labelled airing) | 3,014,129 |
| unlabelled (user, channel, period) rows | 340,159 |
| fast join vs brute-force merge (9 channels, to 2020-06-08) | 47,116 = 47,116 pairs, identical=True |

### Screen time (`src/stats.py` → logs/stats.log; sum vs union: `src/extra_checks.py`)
One row per (user, labelled airing); screen time = summed overlap / duration.

| percentile | 1% | 5% | 10% | 25% | 50% | 75% | 90% | 95% | 99% | max |
|---|---|---|---|---|---|---|---|---|---|---|
| screen time | 0.0047 | 0.0106 | 0.0155 | 0.0437 | 0.1953 | 0.6595 | 1.0 | 1.0 | 1.0 | 31.13 |

- share ≥ 0.8: **20.4363%** (11-20: 17.5362%, p50 0.1730; 21-30: 24.8888%, p50 0.2388)
- share > 1: 0.7964% (24,005 rows, all with n_pieces > 1); rows with n_pieces > 1: 465,732
- ≥ 0.8 by sum 615,977 vs by union 611,760; 4,217 sum-only; sum ≠ union in 42,087 rows

### (user, programme) pairs with ≥ 1 airing at ≥ 0.8 (`src/stats.py`)
| period | pairs | users | programmes | airings per pair (mean) |
|---|---|---|---|---|
| 11-20 | 116,394 | 4,738 | 2,502 | 2.750 |
| 21-30 | 140,919 | 4,643 | 2,850 | 2.100 |

Test users by number of such programmes in 21-30: **≥ 5: 1,150**, 1–4: 88, 0: 22. Of the 1,150, **750** have a tie between the 5th and 6th count.

### Data accounting (`src/stats.py`, section ACCOUNTING)
| quantity | value | source |
|---|---|---|
| raw rows, log | 5,821,987 | dataset11-30.csv |
| raw rows, schedule 11-20 / 21-30 / 31-42 | 1,074,235 / 1,074,394 / 1,295,378 | export_arh_*-final.csv |
| labelled rows (tv_show_id ≠ 0) 11-20 / 21-30 / 31-42 | 115,613 / 121,505 / 144,774 | export_arh_*-final.csv |
| distinct labelled programmes 11-20 / 21-30 / 31-42 | 5,847 / 6,363 / 6,636 | export_arh_*-final.csv |
| log rows after exact-dup drop | 5,821,970 | join.py |
| (view, airing) pairs, any airing | 7,752,415 | join.py |
| joined interactions 11-20 / 21-30 | 1,825,255 / 1,188,874 | artifacts/interactions.parquet |
| interactions ≥ 0.8, 11-20 / 21-30 | 320,081 / 295,896 | artifacts/interactions.parquet |
| users in log | 4,914 | dataset11-30.csv |
| users with interactions 11-20 / 21-30 | 4,841 / 4,806 | interactions |
| users with ≥ 0.8 interaction 11-20 / 21-30 | 4,738 / 4,643 | interactions |
| programmes with interactions 11-20 / 21-30 | 2,976 / 3,222 | interactions |
| programmes with ≥ 0.8 interaction 11-20 / 21-30 | 2,502 / 2,850 | interactions |
| test users | 1,260 | submission.csv |
| cold test users: no view in 11-30 | 0 | log ∩ submission |
| cold test users: no labelled interaction in 11-30 | 2 | interactions ∩ submission |
| cold test users: no ≥ 0.8 interaction in 11-30 | 4 | interactions ∩ submission |
| cold test users: no ≥ 0.8 interaction in 21-30 | 22 | interactions ∩ submission |

### Hand-check rows (`src/stats.py`, seed 42; raw csv lines in logs/stats.log)
1. user 6630914644918865477, ch 1520 *На секретной службе её Величества* [2020-05-26 13:15, 15:35), duration 8400. View 12:24:09–15:31:47 → overlap 15:31:47 − 13:15:00 = 8207 s → 0.9770 ✔
2. user 3903971208799228106, ch 805 *Предатель* [2020-03-20 09:30, 11:20), duration 6600. View 10:33:51–12:06:45 → 11:20:00 − 10:33:51 = 2769 s → 0.4195 ✔
3. user 15187498791851720078, ch 3 *Свадьба вслепую* [2020-06-19 13:45, 15:35), duration 6600. Two views: 11:22:21–13:47:04 → 124 s; 13:47:06–13:51:44 → 278 s; sum 402 → 0.0609 ✔
