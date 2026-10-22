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

## Step 2 — protocol + popularity baseline
- **B7b (resolved)** Over-counting from a user's overlapping views is removed by switching screen time to the union (D11 revised). Effect: 4,217 fewer positives (611,760 vs 615,977); pairs ≥ 0.8 in 21-30 go from 140,919 to 140,298.
- **B13** The step-1 hand-check rows changed after the union refactor. Not a data bug: `groupby(..., sort=False)` became sorted, so seed 42 indexes a different row order. Both sets were checked by hand (RESULTS).
- **B14 (trap for later steps)** The Kaggle target counts *airings*, and airing frequency is extremely skewed: median 4 airings per pool programme, but SpongeBob airs 6,691 times in 31-42, Фиксики 6,621 and Смешарики 4,686; 1,144 programmes air once. A programme's share of positives is largely its number of airings × the user's affinity, so methods that score programmes, not airings, will under-rank high-frequency shows.
- **B15** In validation, "truth outside pool" is 0 by construction (truth airings come from the target schedule itself), so this check cannot detect pool problems. It is only informative for the final pool, where it can't be measured.
- **B16** The channel fallback only touches 103 cohort users / 14 test users, and its effect is within noise: cohort 0.23728 → 0.23684, test subset 0.26775 → 0.26799. On the cold users alone it hurts the cohort (0.165 → 0.145, n = 103) and helps the test subset (0.111 → 0.132, n = 14). Kept because the brief makes it the shared fallback, but with these n it can't be judged.

## Step 3 — methods
- **B17** The ALS optimum sits on the **grid corner** (factors 32, alpha 1, the smallest of each), and plain ALS (0.2024) scores **below popularity** (0.2368). MAP@5 falls monotonically with alpha and factors. Determinism is checked (identical factors on refit), and ALS reproduces history (re-watch share 0.87), so this does not look like an indexing bug. The likely reason is that ALS models a weighted 0/1 preference and drops the count magnitude that the count target and the history ranking rely on. **Not resolved:** the specified grid may not contain the ALS optimum (f < 32, alpha < 1 untested).
- **B18** Selection and reporting use the same validation split (D21). For a 36-point ALS grid, the best row is biased upward; PPR has 4 points, history and content 1 each.
- **B19** PPR iterations are identical for every user (mean = max), as expected: the L1 residual contracts as α^t independent of the start node, so this is not an error in per-user tracking.
- **B20** The airing multiplier helps very differently by method: content +0.074, ALS +0.080, PPR +0.006 at the best α (and it hurts at α ≥ 0.7). It is largest where the base score ignores how often a programme airs, consistent with B14.

## Step 4A
- **B17 (resolved)** The ALS grid corner was the problem: with alpha 0.1/0.3, plain ALS reaches 0.2854 on B (from 0.2024). The fold-A pick (log1p, f = 128, reg = 0.1, alpha = 0.1) is **again on the grid edge**: alpha 0.1 is the lowest value tried and f = 128 the highest, so the optimum may still lie outside the grid. Not extended further.
- **B21** The requested history tie-break (total seconds) is worse than the popularity tie-break on both folds: −0.0099 MAP@5 on A, −0.0069 on B (logs/check_history_ties.log). `s2_history.csv` follows the request; the choice is flagged, not changed.
- **B22** Fold A's truth window (weeks 16-20) includes week 20 with the start of the collection gap (B7d; rows week 20 = 232k vs ~410k). Fold A's target therefore looks somewhat like fold B's, but not like a normal-volume period.
- **B23** `src/s3_methods.py` was removed: its code moved to `src/methods.py` (shared by part A and the hybrids). The step-3 numbers are reproducible at commit `ba2e383`, and fold B reproduces them (RESULTS step 4A, regression line).

## Step 4B
- **B24** `s4b_hybrids.py` imported sklearn/numpy before `methods.py` set `OPENBLAS_NUM_THREADS=1`, so OpenBLAS ran with 14 threads (implicit's warning in the first run log). Fixed by setting the variable at the top of the entry script (also in `s4c`). After the rerun, every MAP / recall / slot number and both submission files are **byte-identical** to the first run; only runtimes moved. `s4a` and `s3` logs show no such warning, and fold B reproduced step 3 exactly.
- **B25** `Components.hist_lists` held history lists for **all** warm users of the split, not only the component users. On the final split (components for 1,256 test users) this put 4,839 users into the H3 frame, and `get_indexer` returned −1 for the extra ones, which **silently indexes the last row** of the score matrices. Those rows were never in the output (test-user lists and files are identical after the fix), but it was a wrong-row bug. Fixed by restricting to component users plus an assertion that every candidate user has a score row. The final frame is now 89,571 rows / 1,256 users.
- **B26** H2's best point is on the edge of the k grid (k = 10, the smaller value), and H1's α is on the grid edge (0.3). Both are within 0.0005 of neighbouring points on A, so this is not chased further.
- **B27** H1 (history-first) is worse than plain PPR × air on both folds (A 0.33404 vs 0.34111; B 0.31407 vs 0.32559), even though history alone is strong. Putting every history programme first by raw count displaces higher-airing programmes the user did not watch in train. 33–35% of truth items are programmes the user never interacted with in train (logs/check_title_transfer.log).
- **B28 — H3 as first committed (0b8cd14) trained a diverged model.** With sklearn's default learning_rate 0.1, the poisson HGB's first boosting step overshoots: training loss 0.752 → 198,672 and validation loss 0.768 → 535,657 after iteration 1, predictions up to 1.05e9 (logs/check_hgb_stopping.log). Labels are positive-airing counts up to 200 against a mean of 0.39, and the log-link Newton step ≈ Σ(y−μ)/Σμ is unbounded (sklearn has no `max_delta_step`). Early stopping then stopped at iteration 10 **without rolling back**, so the committed H3 numbers (A 0.35973, B 0.33493) and `s5_best_hybrid.csv` came from a diverged model that still happened to rank reasonably. The tell was `n_iter_ = 10` on both folds. **Fix:** learning_rate 0.01, max_iter 1000, chosen on fold A among {0.1, 0.05, 0.02, 0.01}; poisson loss and seed unchanged. Results: A 0.37321, B 0.34311 / test 0.38605. `s5_best_hybrid.csv` was regenerated. One of the 5 CV fits on A hits the 1000-iteration cap.
