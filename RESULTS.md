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

## Step 4A — second fold, extended ALS grid, single-method submissions

Command: `.venv/bin/python src/s4a_folds.py` → logs/s4a_folds.log (747 s wall), logs/s4a_grid.csv (all evaluated rows: 315 per fold = popularity 1 + history 4 + ALS 300 + PPR 8 + CBF 2), logs/s4a_selected.json.
Folds (D30): **A** train file 11-20 weeks ≤ 15 → truth weeks 16-20: cohort 4,574 (4,409 warm, 165 cold), test subset 1,212, pool 4,402, 1,376 train programmes. **B** = step-3 split: cohort 4,643, test subset 1,238, pool 6,363.
**Params are chosen on fold A only** (argmax A cohort MAP@5), then reported on B. This table **replaces the step-3 best-of-grid numbers**. "B oracle" = best grid point on B, shown only for reference.

| method | params chosen on A | grid | MAP@5 A cohort | MAP@5 A test | **MAP@5 B cohort** | **MAP@5 B test** | B re-watch | B runtime (s) | B oracle cohort |
|---|---|---|---|---|---|---|---|---|---|
| popularity | — | 1 | 0.24370 | 0.27584 | 0.23684 | 0.26799 | 0.543 | 0.00 | 0.23684 |
| history count (ties: seconds) | — | 1 | 0.32386 | 0.36449 | 0.30671 | 0.35027 | 0.945 | 0.06 | 0.30671 |
| history recency | half-life 4 w | 2 | 0.31811 | 0.35874 | 0.30008 | 0.34509 | 0.945 | 0.11 | 0.30008 |
| history expected count | — | 1 | 0.32312 | 0.36118 | 0.29559 | 0.33877 | 0.945 | 0.06 | 0.29559 |
| ALS | log1p, f = 128, reg = 0.1, alpha = 0.1 | 150 | 0.31649 | 0.35658 | 0.28542 | 0.31797 | 0.912 | 2.36 | 0.28542 |
| ALS × log1p(airings) | count, f = 16, reg = 0.01, alpha = 1 | 150 | 0.31385 | 0.34472 | 0.29041 | 0.31775 | 0.776 | 0.91 | 0.29234 |
| PPR | alpha = 0.7 | 4 | 0.33879 | 0.38095 | 0.31944 | 0.36125 | 0.885 | 43.54 | 0.31944 |
| **PPR × log1p(airings)** | alpha = 0.5 | 4 | **0.34111** | **0.38181** | **0.32559** | **0.36866** | 0.923 | 24.43 | 0.32559 |
| CBF | — | 1 | 0.23688 | 0.26276 | 0.22467 | 0.24891 | 0.598 | 2.98 | 0.22467 |
| CBF × log1p(airings) | — | 1 | 0.31320 | 0.34897 | 0.29870 | 0.33400 | 0.712 | 2.94 | 0.29870 |

- Fold-A selection matches the fold-B oracle for every method except ALS × air (A pick 0.29041 vs B oracle 0.29234 at count, f = 8, reg = 0.01, alpha = 0.3).
- **Extending the ALS grid downward to alpha 0.1/0.3 fixes plain ALS**: 0.2024 at the step-3 corner → 0.2854 at alpha = 0.1, f = 128. The BM25 variant is not selected for either ALS row (full grid in logs/s4a_grid.csv).
- Regression vs step 3 on fold B (same params): ALS (count, 32, 0.01, 1) 0.20239/0.21518, ALS × air (count, 32, 0.1, 1) 0.28206/0.30682, ALS (log1p, 64, 0.1, 10) 0.18942, PPR α 0.7 0.31944/0.36125, CBF × air 0.29870/0.33400, history recency 4 w 0.30008: **all identical** to step 3. History count and expected changed only through the tie-break (D31).
- **Tie-break cost** (`.venv/bin/python src/check_history_ties.py` → logs/check_history_ties.log): history count with ties by seconds vs ties by popularity: A 0.32386 vs **0.33372**, B 0.30671 vs **0.31362** (test subset B 0.35027 vs 0.35617). The seconds tie-break was requested and is used in `s2_history.csv`.
- PPR mass / dangling / convergence checks repeated on A, B and final: max |colsum − 1| = 2.44e-15 / 2.89e-15 / 1.02e-14, synthetic dangling graph 1.000000000000 (0.7200 if dropped), non-converged 0.

### Final single-method files (train 11-30 → 31-42, fold-A params)
Final split: 4,841 warm train users, 3,866 train programmes, pool 6,636; test users 1,260 (1,256 warm, 4 cold → shared fallback).

| file | method | distinct lists | checks |
|---|---|---|---|
| submissions/s2_history.csv | history count, ties by total seconds → popularity | 1,235 | header, 1,260 rows + header, template order, 5 unique ids per row, all ids in 31-42 pool: all True |
| submissions/s3_ppr_air.csv | PPR × log1p(airings), α = 0.5 (21 iterations, 0 non-converged) | 1,183 | all True |

## Step 4B — hybrids (tuned on fold A, reported on fold B)

Command: `.venv/bin/python src/s4b_hybrids.py` → logs/s4b_hybrids.log (352 s wall after the B28 fix), logs/s4b_h2_grid.csv (162 H2 points on A). Components use the fold-A params from logs/s4a_selected.json (PPR × air α 0.5; ALS × air count/16/0.01/1). Definitions: DESIGN D36–D42.

| hybrid | params (chosen on A) | MAP@5 A cohort | MAP@5 A test | **MAP@5 B cohort** | **MAP@5 B test** | cand. recall A | cand. recall B | mean cands B | runtime B: hybrid step (s) | runtime B: its components (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| H1 history-first | PPR α = 0.3 | 0.33404 | 0.37636 | 0.31407 | 0.35699 | 0.6268 | 0.6092 | 33.4 | 0.68 | 15.84 |
| H2 weighted RRF | w_hist 1, w_ppr 1, w_cbf 1, w_als 1, k 10 | 0.34440 | 0.38458 | 0.32921 | 0.36997 | 0.6885 | 0.6827 | 59.9 | 0.18 | 27.11 |
| **H3 HGB poisson re-ranker** | poisson, seed 42, **learning_rate 0.01, max_iter 1000** (early stopping; 786 iterations on A) | **0.37321** (5-fold OOF) | **0.41570** | **0.34311** | **0.38605** | 0.6925 | 0.6939 | 66.6 | 23.95 (B features + fit on A + predict) | 27.11 |
| ~~H3 as first committed (lr 0.1, **diverged**, BUGLOG B28)~~ | defaults, seed 42; stopped at 10 iterations | 0.35973 | 0.40080 | 0.33493 | 0.37482 | 0.6925 | 0.6939 | 66.6 | 7.31 | 27.63 |
| *reference: PPR × air (step 4A)* | α 0.5 | 0.34111 | 0.38181 | 0.32559 | 0.36866 | | | | | 24.43 |

- H1 on A by α: 0.33404 / 0.33377 / 0.33380 / 0.33362 (0.3 / 0.5 / 0.7 / 0.85). H1 sits **below** plain PPR × air on both folds (B 0.31407 vs 0.32559): history-first fixes the slot order on the history count.
- H2: the best A point is all weights 1 with k = 10, i.e. **on the edge of the k grid**. Best with k = 60: 0.34269; history only (other weights 0): 0.32386 (= history count). The top 5 A points lie within 0.0005.
- H3 (fixed): A out-of-fold 0.37321 (CV fold iterations 779 / 611 / 833 / 866 / **1000 = cap**); A in-sample 0.38259, for reference only. Final model fit on B: 842 iterations. Training frames: A 289,475 rows (4,572 users, 11.0% label > 0), B 321,858 rows (4,738 users, 13.1% label > 0).
- Learning-rate check on fold A (`.venv/bin/python src/check_hgb_stopping.py` → logs/check_hgb_stopping.log), with poisson loss, seed 42 and early stopping: lr 0.1 → diverged (validation loss 0.77 → 535,657 after iteration 1, stop at 10, max prediction 1.05e9), A OOF 0.35973; lr 0.05 → diverged (stop at 10), 0.36384; lr 0.02 → 568 iterations, 0.37320; **lr 0.01 → 786 iterations, 0.37321 (chosen, argmax on A)**.
- Fold-A choice of best H2/H3 (D42): **H3** (0.37321 vs 0.34440). B agrees (0.34311 vs 0.32921).

### Slot sources — final predictions, 1,260 test users (6,300 slots)
First source in the order history > PPR > CBF > ALS > popularity whose input contains the item, else fallback (D41). The 20 fallback slots are the 4 cold test users.

| hybrid | history | PPR | CBF | ALS | popularity | fallback |
|---|---|---|---|---|---|---|
| H1 | 6,226 | 54 | 0 | 0 | 0 | 20 |
| H2 | 6,111 | 162 | 5 | 2 | 0 | 20 |
| H3 | 5,400 | 633 | 101 | 117 | 29 | 20 |
| ~~H3 diverged (first commit)~~ | 5,568 | 596 | 69 | 45 | 2 | 20 |

### Files
| file | content | distinct lists | checks |
|---|---|---|---|
| submissions/s4_h1.csv | H1, α 0.3, train 11-30 → 31-42 | 1,220 | header, 1,260 rows + header, template order, 5 unique ids, all ids in 31-42 pool: all True |
| submissions/s5_best_hybrid.csv | H3 (lr 0.01) fit on fold B (321,858 rows, 842 iterations), applied to 11-30 features (89,571 candidate rows, 1,256 warm test users); **regenerated** after B28 | 1,169 | all True |

## Step 4C — H3+ (exposure, length; title transfer checked)

Commands: `.venv/bin/python src/check_title_transfer.py` → logs/check_title_transfer.log; `.venv/bin/python src/s4c_h3plus.py` → logs/s4c_h3plus.log (367 s wall). Definitions: DESIGN D43–D49. Model as fixed in B28 (poisson, lr 0.01, max_iter 1000, seed 42).

### Title-transfer check (item 2)
| fold | truth items | id never in user's train | exact title seen in train under another labelled id | … on id=0 airtime | either |
|---|---|---|---|---|---|
| A | 20,963 | 7,340 (35.01%) | 2 (0.01%) | 16 (0.08%) | 18 (0.09%) |
| B | 21,688 | 7,263 (33.49%) | 6 (0.03%) | 32 (0.15%) | 38 (0.18%) |

Below the 1% bar, so **no title features** were added.

### Exposure inputs
| split | train pieces (labelled + id=0) | hour slots | P(u, channel, hour-of-week) rows | share of candidates with exp_all > 0 |
|---|---|---|---|---|
| A | 2,597,315 | 3,045,325 | 1,614,267 | 0.400 |
| B | 4,923,917 | 5,864,303 | 2,778,632 | 0.501 |
| final (test users) | 7,752,415 | 9,487,403 | 1,415,998 | 0.640 |

Hour-of-week mapping unit-checked (Mon 00:00 → 0, Sun 23:30 → 167, Monday-based week ids).

### H3 vs H3+ (A: 5-fold grouped-by-user out-of-fold; B: fit on all of A)
| model | features | MAP@5 A cohort | MAP@5 A test | **MAP@5 B cohort** | **MAP@5 B test** | cand. recall A | cand. recall B | fit + predict (s) |
|---|---|---|---|---|---|---|---|---|
| H3 | 15 | 0.37321 | 0.41570 | 0.34311 | 0.38605 | 0.6925 | 0.6939 | 90.5 |
| **H3+** | 19 | **0.37585** | **0.41734** | **0.35379** | **0.39499** | 0.6925 | 0.6939 | 87.3 |

Candidates are identical, so recall is identical. Gain: A +0.0026, B **+0.0107** (test subset +0.0089).

### Ablation on fold B (H3+ refit on A without the group → B; drop = H3+ − ablated, positive = the group helps)
| dropped group | features | B cohort | drop | B test | drop |
|---|---|---|---|---|---|
| exposure | exp_all, exp_top3, chan_share | 0.34384 | **+0.00996** | 0.38653 | +0.00846 |
| graph/ALS/content scores | ppr, ppr_rank, als, als_rank, cbf, cbf_rank | 0.34979 | +0.00400 | 0.39084 | +0.00415 |
| history | n_pos, overlap_s, last_week_ago, share_pos | 0.35139 | +0.00241 | 0.39197 | +0.00302 |
| length | med_dur, pos_rate | 0.35352 | +0.00027 | 0.39455 | +0.00045 |
| popularity/airings | pop, air_t, air_tr | 0.35496 | **−0.00117** | 0.39679 | −0.00180 |
| title | not added (< 1% of truth items) | — | — | — | — |

Each row is a single fit with no variance estimate, so drops below ~0.003 should not be read as real (see BUGLOG B30).

### Final file
| file | content | distinct lists | checks |
|---|---|---|---|
| submissions/s6_h3plus.csv | H3+ fit on fold B (321,858 rows, 892 iterations), applied to 11-30 features (89,571 candidate rows, 1,256 warm test users; 4 cold → fallback) | 1,155 | header, 1,260 rows + header, template order, 5 unique ids, all ids in 31-42 pool: all True |

Slot sources (final, 6,300 slots, D41 priority): history 5,178 · PPR 764 · CBF 143 · ALS 152 · popularity 43 · fallback 20.

## Step 5 (part D): push MAP@5 — selected on fold A, reported on fold B
Command: `.venv/bin/python src/s5_push.py > logs/s5_push.log` (all rows also in `logs/s5_rows.csv`; total wall time 3,931 s). Fold A = 5-fold GroupKFold-by-user out-of-fold; fold B = fit on all of A. MAP@5 is over the cohort / the test-user subset of the cohort. Seed 42 unless noted.
Reproduction: the "current" row reproduces step 4C exactly (A 0.37585 / 0.41734, B 0.35379 / 0.39499, recall 0.6925 / 0.6939).

### 1. Candidate sources (H3+ poisson HGB, raw features)
| candidates | mean cands/user A | recall A | recall B | A cohort | A test | B cohort | B test |
|---|---|---|---|---|---|---|---|
| current (history, PPR, CBF, ALS, popularity; top-30) | 61.1 | 0.6925 | 0.6939 | 0.37585 | 0.41734 | **0.35379** | 0.39499 |
| + exposure source top-60, others top-30 | 95.3 | 0.7752 | 0.7640 | **0.37738** | 0.41848 | 0.35256 | 0.39353 |
| + exposure source, top-60 everywhere | 139.1 | **0.7955** | **0.7916** | 0.37614 | 0.41570 | 0.35168 | 0.39300 |

Rule (D51): the highest A recall with A MAP ≥ current → **kept: + exposure source, top-60 everywhere**. Recall +0.10 on both folds, but MAP@5 on B goes *down* for both larger sets (BUGLOG B32).

### 2. Per-week features (current candidates, HGB)
| features | A cohort | A test | B cohort | B test |
|---|---|---|---|---|
| raw (= H3+) | 0.37585 | 0.41734 | **0.35379** | **0.39499** |
| per-week | **0.37600** | 0.41755 | 0.35214 | 0.39363 |
| raw + per-week | 0.37577 | 0.41786 | 0.35224 | 0.39150 |

Kept by argmax A: **per-week**. The A margin is +0.00015, which is noise, and B is −0.00165.

### 4. CatBoostRanker YetiRank (500 iterations, current candidates, raw features), grid on A OOF cohort MAP@5
| lr \ depth | 4 | 6 | 8 |
|---|---|---|---|
| 0.03 | 0.37415 | 0.37651 | **0.37718** |
| 0.1 | 0.37636 | 0.37601 | 0.37587 |

| model | A cohort | A test | B cohort | B test | runtime B (s) |
|---|---|---|---|---|---|
| poisson HGB (H3+) | 0.37585 | 0.41734 | 0.35379 | 0.39499 | 21.0 |
| CatBoost YetiRank lr 0.03 depth 8 | **0.37718** | 0.41785 | 0.35332 | **0.39598** | 30.5 |

Kept: CatBoost (argmax A). The selected point is on the grid edge (depth 8 is the largest value tried). Determinism: two fits with seed 42 give byte-identical predictions, and seed 43 differs (max |Δ| 0.69) (`src/check_cb_determinism.py` → `logs/check_cb_determinism.log`).

### 5. Seed bagging (seeds 42–46, mean of predicted scores)
| model | A cohort | A test | B cohort | B test | runtime B (s) |
|---|---|---|---|---|---|
| CatBoost, 1 seed | 0.37718 | 0.41785 | 0.35332 | 0.39598 | 30.5 |
| CatBoost, 5 seeds | **0.37739** | **0.41852** | **0.35415** | **0.39646** | 124.6 |

### 6. Final table (A: OOF; B: fit on A)
| config | A cohort | A test | B cohort | B test | cand. recall A | cand. recall B | runtime B (s) |
|---|---|---|---|---|---|---|---|
| H3+ (current) | 0.37585 | 0.41734 | 0.35379 | 0.39499 | 0.6925 | 0.6939 | 21.0 |
| candidates: + exposure source (top-60), others top-30 | 0.37738 | 0.41848 | 0.35256 | 0.39353 | 0.7752 | 0.7640 | 29.2 |
| candidates: + exposure source, top-60 everywhere | 0.37614 | 0.41570 | 0.35168 | 0.39300 | 0.7955 | 0.7916 | 33.8 |
| features: per-week | 0.37600 | 0.41755 | 0.35214 | 0.39363 | 0.6925 | 0.6939 | 21.2 |
| features: raw+per-week | 0.37577 | 0.41786 | 0.35224 | 0.39150 | 0.6925 | 0.6939 | 25.1 |
| model: CatBoost YetiRank lr=0.03 depth=8 | 0.37718 | 0.41785 | 0.35332 | 0.39598 | 0.6925 | 0.6939 | 30.5 |
| **seed bagging ×5 (CatBoost)** | **0.37739** | **0.41852** | **0.35415** | **0.39646** | 0.6925 | 0.6939 | 124.6 |
| all kept changes together (top-60 everywhere + exposure; per-week; CatBoost; 5 seeds) | 0.37649 | 0.41741 | 0.35411 | 0.39432 | 0.7955 | 0.7916 | 311.6 |

The best fold-A row is **seed bagging ×5 of CatBoost on current candidates with raw features** (A 0.37739). It beats the runner-up ("+ exposure source, others top-30", 0.37738) by 0.00001, which is a tie in practice (B32). On B it is also the best row: +0.00036 over H3+ on the cohort, +0.00147 on test users. Combining all the kept changes is worse on A than bagging alone.

### s7_best.csv
| file | content | distinct lists | checks |
|---|---|---|---|
| submissions/s7_best.csv | CatBoost YetiRank lr 0.03 depth 8, seeds 42–46, current candidates, raw features; fit on A+B stacked (611,333 rows: A 289,475 + B 321,858; label = positives per target week, D50), applied to 11-30 → 31-42 (89,571 candidate rows, 1,256 warm test users; 4 cold → fallback) | 1,126 | header, 1,260 rows + header, template order, 5 unique ids, all ids in 31-42 pool: all True |

s7 slot sources (6,300 slots, priority history > PPR > CBF > ALS > exposure > popularity, else fallback): history 5,606 · PPR 595 · CBF 34 · ALS 36 · exposure 0 (not a source in the current candidates) · popularity 9 · fallback 20.

### 7. Blend: weighted rank fusion (D56–D58)
Command: `.venv/bin/python src/s5_blend.py > logs/s5_blend.log` (grid: `logs/s5_blend_grid.csv`; wall time 843 s). (a) poisson HGB and (b) CatBoost YetiRank lr 0.03 depth 8 (seed 42), both on the candidates and features kept on A: **+ exposure source, top-60 everywhere; per-week**. (c) H2 RRF with step-4B fold-A weights (all 1, k = 10) on its top-30 lists.

Sanity line (current H3+: current candidates, raw features, HGB): A 0.37585 / 0.41734, B 0.35379 / 0.39499. This reproduces step 4C exactly.

| ranking | A cohort | A test | B cohort | B test |
|---|---|---|---|---|
| (a) HGB, kept cands + per-week | 0.37550 | 0.41645 | 0.35127 | 0.39242 |
| (b) CatBoost, kept cands + per-week | 0.37697 | 0.41812 | 0.35293 | 0.39361 |
| (c) H2 RRF | 0.34440 | 0.38458 | 0.32921 | 0.36997 |
| **blend** w(hgb, cb, h2) = (0.5, 0.5, 0), k = 5 | **0.37830** | **0.41873** | 0.35316 | 0.39339 |

The top of the A grid is H2 weight 0 with equal HGB/CB weights. (0.5, 0.5), (1, 1) and (2, 2) are the same blend, because the score only scales. k = 5 beats k = 20 by 0.00005. The blend beats the best single model on A (+0.00133 over CatBoost), so `s8_blend.csv` was written. On B it beats (a) and (b) but is **below** s7's bagging row (0.35415) and below H3+ (0.35379) (B37).

Pairwise top-5 overlap on fold B (4,540 warm cohort users; each model's own top-5 before fallback):
| pair | mean shared ids (of 5) | users with 0/1/2/3/4/5 shared | identical ordered list |
|---|---|---|---|
| HGB vs CatBoost | 4.469 | 0 / 0 / 10 / 204 / 1,975 / 2,351 | 0.185 |
| HGB vs H2 | 3.642 | 38 / 95 / 369 / 1,216 / 2,055 / 767 | 0.031 |
| CatBoost vs H2 | 3.739 | 28 / 95 / 290 / 1,094 / 2,146 / 887 | 0.048 |

HGB and CatBoost mostly agree on *which* five, but rarely on the order. Fusion therefore mainly reorders the five.

| file | content | distinct lists | checks |
|---|---|---|---|
| submissions/s8_blend.csv | rank fusion (0.5, 0.5, 0), k = 5 of HGB + CatBoost (seed 42 each), fit on A+B stacked (1,350,769 rows, label per target week, D50), kept candidates + per-week features on 11-30 → 31-42 (187,340 ranked rows, 1,256 warm test users; 4 cold → fallback) | 1,055 | header, 1,260 rows + header, template order, 5 unique ids, all ids in 31-42 pool: all True |

s8 slot sources (6,300 slots): history 5,558 · PPR 669 · CBF 29 · ALS 6 · exposure 15 · popularity 3 · fallback 20.

### Final table including the blend
| config | A cohort | A test | B cohort | B test | cand. recall A | cand. recall B | runtime B (s) |
|---|---|---|---|---|---|---|---|
| H3+ (current) | 0.37585 | 0.41734 | 0.35379 | 0.39499 | 0.6925 | 0.6939 | 21.0 |
| seed bagging ×5 (CatBoost) → **s7** | 0.37739 | 0.41852 | **0.35415** | **0.39646** | 0.6925 | 0.6939 | 124.6 |
| all kept changes together | 0.37649 | 0.41741 | 0.35411 | 0.39432 | 0.7955 | 0.7916 | 311.6 |
| blend HGB + CB (kept cands, per-week) → **s8** | **0.37830** | **0.41873** | 0.35316 | 0.39339 | 0.7955 | 0.7916 | 0.1 (fusion step only; the two fits are on top) |

## Morning tasks (after step 5) — no Kaggle submissions
### 1. Hand-check pack
Command: `.venv/bin/python src/hand_check.py > logs/hand_check.log`. The run reproduces the s7 config on fold B exactly (CatBoost ×5 fit on A: cohort 0.35415, test 0.39646). 749 eligible users; picked `2929474010536378025`. Part a) programme 12001682 has 3 log rows and 7 schedule rows. Their `csv_line`s were checked against the raw files with `sed -n`. An independent recomputation from the raw strings matches the code for all 5 truth programmes (positive counts and overlapped airings; values deliberately not printed). Model top 5 on B: 2400480, 2400467, 6500479, 6700482, 20088; code AP@5 = 0.420000. Files and instructions: `analysis/hand_check_user.md`. The code's per-airing values come from `src/hand_check_reveal.py`, to be run after the hand computation.

### 2. s2b_history.csv (history by count, ties → popularity; D59)
Command: `.venv/bin/python src/s2b_history.py > logs/s2b_history.log`
| tie-break | A cohort | A test | B cohort | B test |
|---|---|---|---|---|
| seconds (s2) | 0.32386 | 0.36449 | 0.30671 | 0.35027 |
| **popularity (s2b, chosen on A)** | **0.33372** | **0.37524** | **0.31362** | **0.35617** |

These reproduce `logs/check_history_ties.log` exactly through the new `history_lists(ties=...)`. Validation: header, 1,260 rows + header, template order, 5 unique ids, all ids in the 31-42 pool: all True; 1,218 distinct lists. vs s2: 570 / 1,260 rows identical, 803 with the same id set.

### 3. s7b (prepared, not run; D60, D62, D63)
`src/s7b_perweek.py` writes `submissions/s7b_perweek.csv` when run. It was **not run**; there is no s7b file and no number for it. All 7 count features are rescaled: the train-window ones per active train week (n_pos, overlap_s) or per train week (pop, air_tr), and the target-window ones per target week (air_t, exp_all, exp_top3: A 5, B 10, final 12). Only `--check` was run (`logs/s7b_perweek_check.log`). It builds the A/B frames and finds all 7 columns finite, with means comparable across A / B:

| column | A mean | B mean |
|---|---|---|
| n_pos_pw | 0.1014 | 0.0926 |
| overlap_pw | 468.4 | 423.1 |
| pop_pw | 381.9 | 333.6 |
| air_tr_pw | 53.79 | 50.96 |
| air_t_pw | 52.76 | 48.94 |
| exp_all_pw | 0.3537 | 0.2941 |
| exp_top3_pw | 0.2153 | 0.1773 |

The final split (11-30 → 31-42) frame is built only when the script is actually run.

## Kaggle scores (late submissions, made by the user; reported to me)
The instructor grades the **best private score per student**. All model choices up to and including s8 (and the design of s7b) were made on folds A/B only. Kaggle scores were first seen after s8 was written, and nothing before that used them. s9 was specified after these scores were known (BUGLOG B40).

| file | what | A cohort (OOF) | A test | B cohort (fit on A) | B test | final fit | **Kaggle private** | Kaggle public |
|---|---|---|---|---|---|---|---|---|
| s1_popularity | popularity + channel fallback | 0.24370 | 0.27584 | 0.23684 | 0.26799 | 11-30 counts | **0.28680** | 0.30312 |
| s3_ppr_air | PPR × log1p(airings), α 0.5 | 0.34111 | 0.38181 | 0.32559 | 0.36866 | 11-30 graph | **0.41277** | 0.41415 |
| s6_h3plus | H3+ poisson HGB, raw | 0.37585 | 0.41734 | 0.35379 | 0.39499 | fit on B only | **0.41304** | 0.41277 |
| s7_best | CatBoost ×5 seeds, current cands, raw | 0.37739 | 0.41852 | 0.35415 | 0.39646 | A+B stacked | **0.43013** | 0.43474 |
| s8_blend | HGB + CB rank fusion, exposure + top-60 cands, per-week (B38 bug) | 0.37830 | 0.41873 | 0.35316 | 0.39339 | A+B stacked | **0.44568** | 0.44710 |

Ranking: Kaggle private s8 > s7 > s6 ≈ s3 > s1; fold B s7 > s6 > s8 > s3 > s1; fold A s8 > s7 > s6 > s3 > s1. **Fold A orders the four model files the same way as Kaggle private; fold B does not.** Fold-B gaps between s6, s7 and s8 are ≤ 0.001, but the Kaggle gaps are 0.017 and 0.016. The fold-B gap between s3 and s6 is +0.028, but on Kaggle it is +0.0003. Two differences between validation and final are not exercised by fold B (fit on A only):
1. the final fit's training data: s6 used B only, while s7/s8 used A+B stacked with a per-week label;
2. the final window lengths: 20 train weeks and 12 target weeks, vs 5 → 10 when fitting on A and scoring on B.

These are candidate explanations, not tested.

### s7b and s9 (after the Kaggle scores; not submitted)
Commands: `.venv/bin/python src/s7b_perweek.py > logs/s7b_perweek.log` (528 s), `.venv/bin/python src/s9_blend_pw.py > logs/s9_blend_pw.log` (1,349 s). Standalone re-validation and list comparison: `logs/check_s7b_s9.log`.

| file | what | B cohort (fit on A) | B test | cand. recall B | compared with |
|---|---|---|---|---|---|
| s7_best | CatBoost ×5, current cands, raw | 0.35415 | 0.39646 | 0.6939 | — |
| **s7b_perweek** | s7 with all 7 counts per week + B38 fix (D60, D62, D63) | 0.35414 | 0.39448 | 0.6939 | s7: −0.00001 / −0.00198 |
| s8_blend | HGB + CB (1 seed) fusion, exposure + top-60, per-week (B38 bug) | 0.35316 | 0.39339 | 0.7916 | — |
| **s9_blend_pw** | s8 + B38 fix + all counts per week + CB ×5 seeds (D64) | 0.35415 | 0.39739 | 0.7916 | s8: +0.00099 / +0.00400 |

No fold-A numbers for s7b/s9: they were not specified to be selected on A, and computing them was not part of the request. s9 uses s8's fold-A blend weights (0.5, 0.5, 0), k = 5, without re-tuning.

| file | final fit | final frame | distinct lists | slot sources (history / PPR / CBF / ALS / exposure / popularity / fallback) | checks |
|---|---|---|---|---|---|
| s7b_perweek.csv | A+B stacked, 611,333 rows | 89,571 rows, 1,256 users | 1,033 | 5,642 / 604 / 17 / 12 / 0 / 5 / 20 | all True (in run + standalone) |
| s9_blend_pw.csv | A+B stacked, 1,350,769 rows | 187,340 rows, 1,256 users | 1,048 | 5,539 / 687 / 30 / 7 / 14 / 3 / 20 | all True (in run + standalone) |

List agreement on the 1,260 test users: s7 vs s7b 168 identical rows (mean 4.41 shared ids of 5); s8 vs s9 743 identical (4.83); s7b vs s9 338 identical (4.57).

### s10 (fold C + recency; specified after the Kaggle scores, B42; not submitted)
Command: `.venv/bin/python src/s10_blend_abc.py > logs/s10_blend_abc.log` (4,493 s wall). Config: s9 (D64) + fold C (D65) + recency features (D66); final fit on A+B+C stacked (D67).

Fold C: cohort **4,454** users (1,211 test users); **4,402** of them (1,204 test) have ≥ 1 positive in the C train window; pool 3,275 programmes; 19,739 truth items. C's 3-week target gives fewer positives per user than B's 10 weeks, so its MAP@5 level is not comparable with B's; only compare within a column.

| config | B cohort (fit A) | B test | C cohort (fit A+B) | C test |
|---|---|---|---|---|
| s9 config | 0.35415 | 0.39739 | 0.29470 | 0.31576 |
| + recency | **0.35455** | 0.39616 | **0.29548** | **0.31711** |
| Δ recency | +0.00040 | −0.00123 | +0.00078 | +0.00135 |

The s9 row on B reproduces logs/s9_blend_pw.log exactly. Each cell is one fit (CatBoost 5 seeds + HGB seed 42), with no variance estimate. The recency deltas are the same size as the noise-level margins in B32.

| file | final fit | final frame | distinct lists | slot sources (history / PPR / CBF / ALS / exposure / popularity / fallback) | checks |
|---|---|---|---|---|---|
| s10_blend_abc.csv | A+B+C stacked, 2,058,819 rows (660,856 / 689,913 / 708,050), label ÷5 / ÷10 / ÷3, + recency | 187,340 rows, 1,256 users | 1,031 | 5,643 / 603 / 19 / 3 / 12 / 0 / 20 | all True |
List agreement on the 1,260 test users: s9 vs s10 232 identical rows (mean 4.46 shared ids of 5).

## Kaggle scores — complete (modelling frozen; final = s8_blend.csv, best private 0.44568)
The instructor grades the best private score per student. Choices up to s8 (and the design of s7b) were made on folds A/B only. s9 and s10 were specified after s1–s8 Kaggle scores were known (B40, B42). s7b was prepared before those scores and run after. The final file is s8, which has the best private score; it is chosen *by* Kaggle private, so that score is optimistic as an estimate for new data.

| file | what changed vs the previous model file | A cohort (OOF) | B cohort (fit A) | B test | C cohort (fit A+B) | **Kaggle private** | Kaggle public |
|---|---|---|---|---|---|---|---|
| s1_popularity | popularity + channel fallback | 0.24370 | 0.23684 | 0.26799 | — | 0.28680 | 0.30312 |
| s3_ppr_air | personalized PageRank × log1p(airings) | 0.34111 | 0.32559 | 0.36866 | — | 0.41277 | 0.41415 |
| s6_h3plus | poisson-HGB re-ranker + exposure/length features; final fit on B only | 0.37585 | 0.35379 | 0.39499 | — | 0.41304 | 0.41277 |
| s7_best | CatBoost YetiRank ×5 seeds; final fit on A+B stacked; raw counts | 0.37739 | 0.35415 | 0.39646 | — | 0.43013 | 0.43474 |
| **s8_blend (final)** | HGB + CatBoost rank fusion; exposure + top-60 candidates; per-week features (B38 bug) | 0.37830 | 0.35316 | 0.39339 | — | **0.44568** | 0.44710 |
| s7b_perweek | s7 with all 7 counts per week + B38 fix | — | 0.35414 | 0.39448 | — | 0.44495 | 0.44515 |
| s9_blend_pw | s8 + B38 fix + all counts per week + CatBoost ×5 *(after Kaggle)* | — | 0.35415 | 0.39739 | — | 0.44534 | 0.44831 |
| s10_blend_abc | s9 + fold C + recency features; final fit on A+B+C *(after Kaggle)* | — | 0.35455 | 0.39616 | 0.29548 | 0.44073 | 0.44500 |

(s2_history, s2b_history, s4_h1, s5_best_hybrid were not submitted.)

Findings, each limited to what one submission pair shows (one private score per file; no variance estimate; private-set size unknown):
- **Per-week rescaling:** s7 → s7b changes only the count features (per week, with the B38 fix), and private goes 0.43013 → **0.44495 (+0.0148)**. On fold B the same change was neutral (0.35415 → 0.35414): fold B, fit on A, does not exercise the A+B-stacked final fit, where feature scales differ between the stacked parts and the 20-week final window (B33). This is consistent with that scale mismatch being what hurt s7, but one pair of submissions cannot establish it.
- **Fold C:** s9 → s10 adds fold C and recency features together, and private drops 0.44534 → **0.44073 (−0.0046)**. The two changes are confounded. One plausible reason is that C's train window ends in the low-volume collection-gap weeks 21-27 (pair rows ~142k–297k per week vs ~410k–560k in weeks 11-19 and 28-30), so C rows teach the model from thin recent history. This is not tested.
- s8 → s9 (B38 fix + per-week target counts + CatBoost ×5): private 0.44568 → 0.44534 (−0.0003), public +0.0012. That is within the public/private disagreement seen elsewhere (up to 0.016 for s1).
- Fold-A OOF orders s3 < s6 < s7 < s8 the same way as Kaggle private; fold B does not (B40).

## Step 6 — report examples (fold B, same two users for every method)
Command: `.venv/bin/python src/examples.py > logs/examples.log` (tables also in logs/examples.md). Rule: DESIGN D68. Check: each method's fold-B MAP@5 recomputed in this run equals RESULTS (popularity 0.23684, history 0.30671, PPR × air 0.32559, CBF × air 0.29870, ALS × air 0.29041, s8 blend 0.35316 / 0.39339). Heavy threshold = 173 train positive airings (90th percentile over the 1,260 test users); eligible heavy 127, light 23.

Tags: **R** = re-watch (the user had ≥ 1 positive airing of this programme in train 11-20); **T** = in the user's 21-30 truth; **f** = slot filled by the shared fallback, not by the method.

#### heavy viewer `3086774348345899441`: 252 train positive airings over 47 programmes (weeks 11-20); 5 truth programmes in 21-30

Train history top-10 (11-20):

| # | id | title | category | positives |
|---|---|---|---|---|
| 1 | 12001682 | М/с 'Губка Боб Квадратные Штаны'. | Детям | 103 |
| 2 | 12001734 | М/с 'Волшебные покровители'. | Детям | 28 |
| 3 | 12002201 | М/с 'Маша и Медведь'. | Детям | 19 |
| 4 | 12002856 | М/с 'Элвиннн!!! и бурундуки'. | Детям | 16 |
| 5 | 240081 | Факты. | Инфо | 14 |
| 6 | 2400508 | Сегодня. | Инфо | 13 |
| 7 | 12002753 | М/с 'Санджей и Крейг'. | Детям | 7 |
| 8 | 12002771 | М/с 'Черепашки-ниндзя'. | Детям | 5 |
| 9 | 12002955 | М/с 'Свинка Пеппа'. | Детям | 4 |
| 10 | 2400467 | 'Викна-Новости'. | Инфо | 2 |

Truth 21-30 (in order): 12001682 М/с 'Губка Боб Квадратные Штаны'., 240081 Факты., 2400508 Сегодня., 12001734 М/с 'Волшебные покровители'., 12002856 М/с 'Элвиннн!!! и бурундуки'.

| method | AP@5 | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| popularity | 0.353 | 2400480 ТСН. (Инфо) **R** | 240081 Факты. (Инфо) **RT** | 12001682 М/с 'Губка Боб Квадратные Штаны'. (Детям) **RT** | 20088 'Завтрак с 1+1'. Информационно-развлекательная программа. (Развлечения) **R** | 2400508 Сегодня. (Инфо) **RT** |
| history (count) | 0.710 | 12001682 М/с 'Губка Боб Квадратные Штаны'. (Детям) **RT** | 12001734 М/с 'Волшебные покровители'. (Детям) **RT** | 12002201 М/с 'Маша и Медведь'. (Детям) **R** | 12002856 М/с 'Элвиннн!!! и бурундуки'. (Детям) **RT** | 240081 Факты. (Инфо) **RT** |
| PPR x air (alpha 0.5) | 0.760 | 12001682 М/с 'Губка Боб Квадратные Штаны'. (Детям) **RT** | 12001734 М/с 'Волшебные покровители'. (Детям) **RT** | 12002856 М/с 'Элвиннн!!! и бурундуки'. (Детям) **RT** | 12002201 М/с 'Маша и Медведь'. (Детям) **R** | 240081 Факты. (Инфо) **RT** |
| CBF x air | 0.600 | 12001682 М/с 'Губка Боб Квадратные Штаны'. (Детям) **RT** | 12002856 М/с 'Элвиннн!!! и бурундуки'. (Детям) **RT** | 12001734 М/с 'Волшебные покровители'. (Детям) **RT** | 12002896 М/с 'Вспыш и чудо-машинки', 2 сезон, 14 с. 'Унесённый лыжами'. (Детям) | 12001732 М/с 'Пингвины из 'Мадагаскара'. (Детям) **R** |
| ALS x air (count, f=16, reg=0.01, alpha=1) | 0.600 | 12001682 М/с 'Губка Боб Квадратные Штаны'. (Детям) **RT** | 12002856 М/с 'Элвиннн!!! и бурундуки'. (Детям) **RT** | 12001734 М/с 'Волшебные покровители'. (Детям) **RT** | 2400480 ТСН. (Инфо) **R** | 12002355 М/с 'Кунг-фу панда: Удивительные легенды'. (Детям) **R** |
| s8 blend (HGB + CatBoost rank fusion) | 1.000 | 12001682 М/с 'Губка Боб Квадратные Штаны'. (Детям) **RT** | 12002856 М/с 'Элвиннн!!! и бурундуки'. (Детям) **RT** | 12001734 М/с 'Волшебные покровители'. (Детям) **RT** | 240081 Факты. (Инфо) **RT** | 2400508 Сегодня. (Инфо) **RT** |

#### light viewer `14394187406328124815`: 1 train positive airings over 1 programmes (weeks 11-20); 1 truth programmes in 21-30

Train history top-10 (11-20):

| # | id | title | category | positives |
|---|---|---|---|---|
| 1 | 1000376 | Т/с 'Друзья', 1 сезон, 5 с. | Сериалы | 1 |

Truth 21-30 (in order): 1000376 Т/с 'Друзья', 1 сезон, 5 с.

| method | AP@5 | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| popularity | 0.000 | 2400480 ТСН. (Инфо) | 240081 Факты. (Инфо) | 12001682 М/с 'Губка Боб Квадратные Штаны'. (Детям) | 20088 'Завтрак с 1+1'. Информационно-развлекательная программа. (Развлечения) | 2400508 Сегодня. (Инфо) |
| history (count) | 1.000 | 1000376 Т/с 'Друзья', 1 сезон, 5 с. (Сериалы) **RT** | 12001682 М/с 'Губка Боб Квадратные Штаны'. (Детям) **f** | 2400480 ТСН. (Инфо) **f** | 240081 Факты. (Инфо) **f** | 2400467 'Викна-Новости'. (Инфо) **f** |
| PPR x air (alpha 0.5) | 1.000 | 1000376 Т/с 'Друзья', 1 сезон, 5 с. (Сериалы) **RT** | 2400480 ТСН. (Инфо) | 12001682 М/с 'Губка Боб Квадратные Штаны'. (Детям) | 10001514 Т/с 'Теория большого взрыва', 2 сезон, 15 с. (Сериалы) | 240081 Факты. (Инфо) |
| CBF x air | 1.000 | 1000376 Т/с 'Друзья', 1 сезон, 5 с. (Сериалы) **RT** | 10001514 Т/с 'Теория большого взрыва', 2 сезон, 15 с. (Сериалы) | 1000405 Т/с 'Клиника', 2 сезон, 19 с. (Сериалы) | 10001903 Т/с 'Американская семейка', 9 сезон, 9 с. (Сериалы) | 10002810 Т/с 'Бруклин 9-9', 6 сезон, 17 с. (Сериалы) |
| ALS x air (count, f=16, reg=0.01, alpha=1) | 1.000 | 1000376 Т/с 'Друзья', 1 сезон, 5 с. (Сериалы) **RT** | 10001514 Т/с 'Теория большого взрыва', 2 сезон, 15 с. (Сериалы) | 1000589 Т/с 'Отчаянные домохозяйки', 5 сезон, 17 с. 'История Люси и Джесси'. (Сериалы) | 1000405 Т/с 'Клиника', 2 сезон, 19 с. (Сериалы) | 12001712 М/с 'Симпсоны'. (Детям) |
| s8 blend (HGB + CatBoost rank fusion) | 1.000 | 1000376 Т/с 'Друзья', 1 сезон, 5 с. (Сериалы) **RT** | 10001336 Т/с 'Кости', 9 сезон, 21 с. 'Случай с холодом'. (Сериалы) | 2400480 ТСН. (Инфо) | 12001682 М/с 'Губка Боб Квадратные Штаны'. (Детям) | 12001712 М/с 'Симпсоны'. (Детям) |

### Step 6 — other report inputs
- **Labelled share of viewing** (`logs/check_labelled_share.log`, inline script over `artifacts/view_airing_pairs.parquet`): labelled airings receive 54.82% (11-20), 58.43% (21-30) and 56.43% (all) of viewed overlap seconds. They are only 10.76–11.31% of schedule rows and 15.97–16.90% of airtime (B11). The report therefore says "10.8% of schedule rows", not "10.8% of airtime".
- **References:** six records fetched and saved in `analysis/refs/` (4 Crossref JSON, 1 PMLR page, 1 Kaggle page; index in `analysis/refs/README.md`).
- **Report:** `report/report.md` → `report/report.pdf` via `report/build_pdf.py` (python-markdown 3.7 + headless Chrome). 9 A4 pages, single column, including references and the two placeholders. Every page was rendered to PNG with PDFKit and inspected.

### Light viewer, rule 2 (DESIGN D69: rule 1 was degenerate — single truth item = single history item, every personalised method AP 1.0)
Same run as above (`logs/examples.log`): eligible 21; picked `706288898823145641`.

#### light (rule 2: >= 3 truth programmes) viewer `706288898823145641`: 2 train positive airings over 2 programmes (weeks 11-20); 5 truth programmes in 21-30

Train history top-10 (11-20):

| # | id | title | category | positives |
|---|---|---|---|---|
| 1 | 90044148 | Х/ф 'Волга-Волга'. | Фильмы | 1 |
| 2 | 90055479 | Х/ф 'SWAT: Спецназ города ангелов'. | Фильмы | 1 |

Truth 21-30 (in order): 240081 Факты., 2400480 ТСН., 10003012 Т/с 'Однажды в Одессе'., 2400467 'Викна-Новости'., 10002515 Т/с 'Мамочки', 1 сезон, 19 и 20 с.

| method | AP@5 | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| popularity | 0.400 | 2400480 ТСН. (Инфо) **T** | 240081 Факты. (Инфо) **T** | 12001682 М/с 'Губка Боб Квадратные Штаны'. (Детям) | 20088 'Завтрак с 1+1'. Информационно-развлекательная программа. (Развлечения) | 2400508 Сегодня. (Инфо) |
| history (count) | 0.000 | 90044148 Х/ф 'Волга-Волга'. (Фильмы) **R** | 90055479 Х/ф 'SWAT: Спецназ города ангелов'. (Фильмы) **R** | 10001261 Т/с 'Мыслить как преступник'. (Сериалы) **f** | 1000381 Т/с 'CSI: Место преступления', 7 сезон, 6 и 7 с. (Сериалы) **f** | 90077217 Х/ф 'Геракл: Начало легенды'. (Фильмы) **f** |
| PPR x air (alpha 0.5) | 0.167 | 90055479 Х/ф 'SWAT: Спецназ города ангелов'. (Фильмы) **R** | 90044148 Х/ф 'Волга-Волга'. (Фильмы) **R** | 2400480 ТСН. (Инфо) **T** | 240081 Факты. (Инфо) **T** | 12001682 М/с 'Губка Боб Квадратные Штаны'. (Детям) |
| CBF x air | 0.000 | 90055479 Х/ф 'SWAT: Спецназ города ангелов'. (Фильмы) **R** | 90044148 Х/ф 'Волга-Волга'. (Фильмы) **R** | 90044710 Исторический прайм. Х/ф 'Цирк'. (Фильмы) | 90073000 Х/ф 'Инопланетное вторжение: Битва за Лос-Анджелес'. (Фильмы) | 90037720 Исторический прайм. Х/ф 'Веселые ребята'. (Фильмы) |
| ALS x air (count, f=16, reg=0.01, alpha=1) | 0.000 | 2400340 Служба розыска детей. (Инфо) | 10002744 Т/с 'Майор и магия', 8 с. (Сериалы) | 12002378 М/с 'Удивительный мир Гамбола'. (Детям) | 1000289 Т/с 'Остаться в живых', 1 сезон, 1 с. 'Таинственный остров - часть 1'. (Сериалы) | 5900347 'Деньги'. (Инфо) |
| s8 blend (HGB + CatBoost rank fusion) | 0.400 | 2400480 ТСН. (Инфо) **T** | 240081 Факты. (Инфо) **T** | 12001682 М/с 'Губка Боб Квадратные Штаны'. (Детям) | 12002955 М/с 'Свинка Пеппа'. (Детям) | 90080832 Х/ф 'Безбашенные'. (Фильмы) |
