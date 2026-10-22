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

### Screen time (`src/stats.py` → logs/stats.log)
One row per (user, labelled airing). **Used since step 2: union of the user's overlapping pieces / duration, clipped to 1** (DESIGN D11). Step-1 sum version kept for comparison.

| percentile | 1% | 5% | 10% | 25% | 50% | 75% | 90% | 95% | 99% | max |
|---|---|---|---|---|---|---|---|---|---|---|
| **union (used)** | 0.0047 | 0.0106 | 0.0155 | 0.0437 | 0.1950 | 0.6567 | 1.0 | 1.0 | 1.0 | 1.0 |
| sum (step 1) | 0.0047 | 0.0106 | 0.0155 | 0.0437 | 0.1953 | 0.6595 | 1.0 | 1.0 | 1.0 | 31.13 |

| | union (used) | sum (step 1) |
|---|---|---|
| share ≥ 0.8, all | **20.2964%** (611,760) | 20.4363% (615,977) |
| share ≥ 0.8, 11-20 (p50) | 17.3698% (317,043; 0.1727) | 17.5362% (320,081; 0.1730) |
| share ≥ 0.8, 21-30 (p50) | 24.7896% (294,717; 0.2385) | 24.8888% (295,896; 0.2388) |
| rows > 1 | 0 (clip never active: `join.py` prints 0) | 24,005 (all n_pieces > 1) |

- union ≠ sum in 42,087 rows; 4,217 rows are positive only under sum; rows with n_pieces > 1: 465,732
- union verified against a naive per-group interval merge: 38,889 groups (4,902 multi-piece), identical (`src/check_join.py` → logs/check_join.log)

### (user, programme) pairs with ≥ 1 airing at ≥ 0.8 (`src/stats.py`)
| period | pairs (union) | users | programmes | airings per pair (mean) | pairs (sum, step 1) |
|---|---|---|---|---|---|
| 11-20 | 115,325 | 4,738 | 2,501 | 2.749 | 116,394 |
| 21-30 | 140,298 | 4,643 | 2,848 | 2.101 | 140,919 |

Test users by number of such programmes in 21-30 (union): **≥ 5: 1,150**, 1–4: 88, 0: 22 (same as sum). Of the 1,150, **751** (sum: 750) have a tie between the 5th and 6th count, which the step-2 truth breaks by overlap seconds and then id.

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
| interactions ≥ 0.8 (union), 11-20 / 21-30 | 317,043 / 294,717 (sum: 320,081 / 295,896) | artifacts/interactions.parquet |
| users in log | 4,914 | dataset11-30.csv |
| users with interactions 11-20 / 21-30 | 4,841 / 4,806 | interactions |
| users with ≥ 0.8 interaction 11-20 / 21-30 | 4,738 / 4,643 | interactions |
| programmes with interactions 11-20 / 21-30 | 2,976 / 3,222 | interactions |
| programmes with ≥ 0.8 interaction (union) 11-20 / 21-30 | 2,501 / 2,848 (sum: 2,502 / 2,850) | interactions |
| test users | 1,260 | submission.csv |
| cold test users: no view in 11-30 | 0 | log ∩ submission |
| cold test users: no labelled interaction in 11-30 | 2 | interactions ∩ submission |
| cold test users: no ≥ 0.8 interaction in 11-30 | 4 | interactions ∩ submission |
| cold test users: no ≥ 0.8 interaction in 21-30 | 22 | interactions ∩ submission |

### Hand-check rows (`src/stats.py`, seed 42; raw csv lines in logs/stats.log)
After the union change, interactions are sorted by (user, airing), so seed 42 now picks different rows than at commit e0ce54a. Those three earlier rows were checked by hand too: 8207 s, 2769 s, 124 + 278 = 402 s.
1. user 11971046114677874454, ch 23 *Месть природы* [2020-07-17 09:55, 11:25), duration 5400. View 10:15:58–10:19:15 → 197 s → 0.0365 ✔
2. user 1792151577962019890, ch 3 *Мир наизнанку* [2020-05-10 09:25, 15:45), duration 22800. Three disjoint views: 300 + 134 + 588 = 1022 s → 0.0448 ✔
3. user 14287208251067546691, ch 5 *В тылу врага, 2 ч.* [2020-05-20 13:25, 13:50), duration 1500. View 10:16:16–16:05:27 covers it all → 1500 s → 1.0 ✔
4. (row with union ≠ sum) user 15116560307644600082, ch 3 *ЧистоNews* [2020-05-14 20:35, 20:45), duration 600. Views 18:23:40–21:41:21 and 20:23:57–01:02:47 **both** cover the whole airing → sum 1200 s, union 600 s → 1.0 ✔

## Step 2 — protocol + popularity baseline

Commands: `.venv/bin/python -m unittest discover -s tests -v` → logs/tests.log; `.venv/bin/python src/s1_popularity.py` → logs/s1_popularity.log. Screen time = union (D11).

### Metric unit tests (logs/tests.log): 4 tests, all OK
- slide example, truth {A,B,C}: `A B D C E` → 0.9167, `D A E B C` → 0.5333 (hand derivation in tests/test_protocol.py)
- edge cases (truth longer than 5, single-item truth, empty list) and the truth tie-break order

### Validation cohort (train 11-20 → truth 21-30)
| | all users | test users (subset) |
|---|---|---|
| evaluable (≥ 1 positive in 21-30) | **4,643** | **1,238** of 1,260 |
| no truth | 252 of the users with labelled interactions in 11-30 (4,914 log users − 4,643 = 271 incl. users without labelled views) | 22 |
| evaluable but no positive in 11-20 (cold → fallback) | 103 | 14 |

Truth length in the cohort: 1: 158, 2: 152, 3: 136, 4: 167, 5: 4,030.

### Candidate pool
| | validation (21-30) | final (31-42) |
|---|---|---|
| pool size (labelled programmes in target schedule) | 6,363 | 6,636 |
| truth slots outside pool | 0 of 21,688 (by construction: truth airings come from the same schedule) | unknown |
| airings per programme: median / mean / p90 / max | 4 / 19.10 / 18 / 6,132 | 4 / 21.82 / 20 / 6,691 |
| programmes airing once | 1,162 | 1,144 |
| pool programmes with 0 train positives | 4,488 | — |

Top 10 by airings in 31-42: SpongeBob 6,691; Фиксики 6,621; Смешарики 4,686; Gumball 2,986; Alvin 2,088; Simpsons 2,032; Пойми меня 2,016; Моланг 1,912; Peppa Pig 1,826; Friends 1,651. Nine of the 10 are kids' cartoons; the full list for both periods with ids is in logs/s1_popularity.log.

### Popularity baseline — validation MAP@5
| method | cohort (n = 4,643) | test subset (n = 1,238) | cold cohort (n = 103) | cold test (n = 14) |
|---|---|---|---|---|
| popularity, no fallback (global list for all) | **0.23728** | **0.26775** | 0.16465 | 0.11095 |
| popularity + channel fallback for cold users | **0.23684** | **0.26799** | 0.14487 | 0.13214 |

Global top-5 from 11-20 positives: 2400480 (39,944 positives), 240081 (27,032), 12001682 SpongeBob (26,220), 20088 Завтрак с 1+1 (12,796), 2400508 (10,831).

### Final submission `submissions/s1_popularity.csv`
- trained on 11-30 positives; top-5 = 2400480, 12001682, 240081, 20088, 2400508
- 1,256 test users get the global list; 4 get the channel fallback; 4 distinct lists in total
- checks (all True): header == template, 1,260 rows + header (1,261 lines), user order == template, 5 unique ids per row, all ids integers in the 31-42 pool

## Step 3 — methods and components, each alone on validation

Command: `.venv/bin/python src/s3_methods.py` → logs/s3_methods.log (summary + checks), logs/s3_grid.csv (all 87 evaluated rows: 72 ALS grid rows + 15 others).
Protocol: train 11-20 → truth 21-30, cohort 4,643 users (4,540 warm with train positives, 103 cold → shared fallback), test subset 1,238, pool 6,363, MAP@5 (D16). Short lists are topped up from the shared fallback (D17), whose 5.83 s build is shared and **not** included in per-method runtime. Runtime = fit + score + rank for the cohort on one CPU process (BLAS 1 thread). Parameters are selected on validation cohort MAP@5 (D21), so the best-of-grid rows are optimistic.

| method | params (selected on validation) | MAP@5 cohort (n = 4,643) | MAP@5 test subset (n = 1,238) | re-watch share of 5 slots | runtime (s) |
|---|---|---|---|---|---|
| popularity (reference, = step 2) | global top-5; fallback for cold | 0.23684 | 0.26799 | 0.543 | 0.00 |
| a) history (1) | score = train positive count | 0.31362 | 0.35617 | 0.945 | 0.05 |
| a) history (2) | recency-weighted count, half-life 2 w | 0.28248 | 0.32271 | 0.945 | 0.08 |
| a) history (2) | recency-weighted count, half-life 4 w | 0.30008 | 0.34509 | 0.945 | 0.11 |
| a) history (3) | expected count = pos per train airing × target airings | 0.29560 | 0.33879 | 0.945 | 0.05 |
| b) ALS | conf = count, f = 32, reg = 0.01, alpha = 1 | 0.20239 | 0.21518 | 0.869 | 1.30 |
| b+e) ALS × log1p(airings) | conf = count, f = 32, reg = 0.1, alpha = 1 | 0.28206 | 0.30682 | 0.845 | 1.22 |
| c) PPR | alpha = 0.7 | 0.31944 | 0.36125 | 0.885 | 47.04 |
| c+e) PPR × log1p(airings) | alpha = 0.5 | **0.32559** | **0.36866** | 0.923 | 24.33 |
| d) content tf-idf | cosine(profile, item) | 0.22467 | 0.24891 | 0.598 | 3.70 |
| d+e) content tf-idf × log1p(airings) | cosine(profile, item) | 0.29870 | 0.33400 | 0.712 | 3.66 |

### Grids (logs/s3_grid.csv)
ALS, MAP@5 cohort (rows conf / factors, columns reg / alpha):

| conf, f | .01/1 | .01/10 | .01/40 | .1/1 | .1/10 | .1/40 |
|---|---|---|---|---|---|---|
| count, 32 | **0.2024** | 0.1667 | 0.1085 | 0.2007 | 0.1671 | 0.1047 |
| count, 64 | 0.1791 | 0.1682 | 0.1157 | 0.1776 | 0.1705 | 0.1161 |
| count, 128 | 0.1777 | 0.1750 | 0.1538 | 0.1792 | 0.1748 | 0.1488 |
| log1p, 32 | 0.1857 | 0.1879 | 0.1305 | 0.1854 | 0.1886 | 0.1336 |
| log1p, 64 | 0.1624 | 0.1893 | 0.1402 | 0.1626 | 0.1894 | 0.1425 |
| log1p, 128 | 0.1648 | 0.1785 | 0.1693 | 0.1650 | 0.1742 | 0.1658 |

ALS × log1p(airings): best 0.2821 (count, 32, 0.1, 1); range 0.1600–0.2821. The full table is in the log.
The ALS optimum is at the **grid corner** (fewest factors, smallest alpha); reg changes MAP@5 by ≤ 0.0051 for plain ALS and by up to 0.0353 for ALS × log1p(airings) (count, f 32, alpha 40). Two fits of the selected config give identical item factors (max abs diff 0.0).

PPR (cohort / test; convergence):

| alpha | PPR | PPR × log1p(airings) | mean iter | max iter | max residual (L1) | non-converged |
|---|---|---|---|---|---|---|
| 0.3 | 0.31456 / 0.35733 | 0.32293 / 0.36567 | 13.0 | 13 | 3.19e-07 | 0 |
| 0.5 | 0.31816 / 0.36017 | **0.32559 / 0.36866** | 21.0 | 21 | 9.54e-07 | 0 |
| 0.7 | **0.31944 / 0.36125** | 0.31792 / 0.35598 | 41.0 | 41 | 8.91e-07 | 0 |
| 0.85 | 0.29859 / 0.33621 | 0.29221 / 0.32664 | 90.0 | 90 | 8.89e-07 | 0 |

PPR checks: after one update from one-hot restarts on the real graph (500 users, α = 0.85), max |column sum − 1| = 2.89e-15 and min entry = 0. The real graph has 0 dangling nodes, so a synthetic graph with a dangling item holding 0.4 mass is used too: column sum after the update = 1.000000000000 with the dangling return, 0.7200 if that mass were dropped.

Graph / matrix sizes: 4,738 train users × 2,501 train programmes, 115,325 edges; 1,875 train programmes are in the pool, so ALS and PPR can only rank those, and the rest come from fallback. Content: 6,989 items, vocabulary 13,791 tokens (cat 8, genres 66, channels 190, directors 3,808, actors 9,719); 0 pool items without tokens.
