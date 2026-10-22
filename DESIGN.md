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
| D8 | Join: view ↔ airing when `vsetv_id == channel_id` and `min(stops) − max(starts) > 0`; per-channel searchsorted with key `channel·1e11 + epoch_s`; lower bound uses running max of airing ends (correct with overlapping airings) | no cartesian merge; verified identical to brute-force merge on a 9-channel sample to 2020-06-08 (47,116 pairs, `src/check_join.py`) | — |
| D9 | Airings with `duration == 0` are excluded from the join | screen time undefined (1 row, unlabelled) | — |
| D10 | 17 exact duplicate log rows dropped before join | identical rows would double-count overlap | keep them (effect ≤ 17 views) |
| D11 | ~~superseded in step 2, see D11 (revised)~~ Screen time = **sum** of the overlaps of all the user's views with that airing / airing duration, not clipped | as specified in the task | **open:** union of intervals. Sum > union for 42,087 rows because the same user has overlapping views on one channel (multi-device?); 4,217 rows cross 0.8 only under sum. Kaggle's exact rule is unknown, so revisit when validating against the leaderboard |
| D12 | Unlabelled airtime (`tv_show_id == 0`) kept only as `artifacts/unlab_seconds.parquet`: seconds per (user, channel, period) | not an item, but a possible feature | — |
| D13 | The positive threshold `screen_time >= 0.8` is inclusive | matches "≥ 0.8" in the competition description | — |

### Revisions after step 1 (decided by the user)
- **D11 (revised)** Screen time = **union** of the user's overlapping pieces on one airing / airing duration, **clipped to 1** (`join.union_seconds`). Clip is a no-op because the pieces are already clipped to the airing (0 rows > 1). Sum is kept as `screen_time_sum` / `overlap_sum_s` for comparison only.
- **D19** The weeks 20–27 collection gap (BUGLOG B7d) stays a documented limitation; no reweighting or fix.

## Step 2 — protocol + popularity baseline

| # | Decision | Why | Alternatives / open |
|---|---|---|---|
| D14 | Splits: validation = train 11-20 → truth 21-30; final = train 11-30 → predict 31-42. Period = airing's source file (D6) | as specified | — |
| D15 | Truth per user: programmes with ≥ 1 positive airing (union screen time ≥ 0.8) in the target period, sorted by #positive airings desc → **total union overlap seconds of the user on that programme in the target period, over all its airings (positive or not)** desc → tv_show_id asc; top 5 (fewer if the user has fewer) | as specified; "total overlap seconds" is taken over all airings, not only positive ones | only-positive airings for the tie-break |
| D16 | MAP@5 = mean over the cohort of AP@5 / min(5, len(truth)); cohort = users with ≥ 1 positive in the target period. Also reported on the test-user subset | as specified; a user without a prediction scores 0 | — |
| D17 | **Shared fallback** for users with no positive in train: score(u, p) = train positives(p) × Σ over the channels where p airs in the target schedule of u's share of train watch seconds on that channel (labelled union seconds + id=0 seconds); programmes with score > 0 ranked desc (ties by global rank), then filled from global pool popularity. Users with no train seconds get global popularity | "popular in the pool on the user's own channels"; weighting by channel share keeps one formula for users with one channel or many | rank channels first, then programmes within a channel; open to revisit |
| D18 | Popularity = pool programmes ranked by #positive airings in train desc → total train overlap seconds desc → id asc. Pool = labelled programmes in the target schedule; previously watched programmes are allowed (repeats); every list has exactly 5 unique pool ids (`protocol.check_lists` asserts it) | as specified; the same pool is used for every method | — |
| D20 | Submission ids are written as plain integers separated by single spaces, user_id as the original string, in template row order | template format | — |

## Step 3 — methods/components, each alone on validation

All rows use the step-2 protocol: cohort = 4,643 users with ≥ 1 positive in 21-30, test subset = 1,238, pool = 6,363 labelled programmes in the 21-30 schedule, MAP@5 as D16. Each method produces a ranked list for **warm** users (≥ 1 train positive); that list is truncated to 5 and topped up from the user's **shared fallback list** (D17). Cold users get the shared fallback only. `protocol.check_lists` asserts 5 unique pool ids for every user in every row.

| # | Decision | Why | Alternatives / open |
|---|---|---|---|
| D21 | Parameters are selected **only on validation cohort MAP@5**. The table reports the best grid point per method variant and the full grid is in `logs/s3_grid.csv`, so the reported maxima are optimistic (selected and reported on the same split) | there is no second validation split yet | a held-out split, e.g. weeks 28-30 inside train, for selection |
| D22 | Re-watch share = mean over cohort users of the share of the 5 slots holding a programme the user had ≥ 1 positive airing of in train (11-20). Fallback slots count too | measures how much a method just repeats history | "watched at all" (any overlap) instead of positive |
| D23 | Ties inside every method: score desc, then global pool popularity rank (D18). History also uses n_pos before popularity | deterministic, same tie-break for all methods | — |
| D24 | History (a): items = the user's train-positive programmes that are in the pool. (1) n_pos; (2) Σ over positive airings of 0.5^(age/h), age = weeks from airing start to 2020-05-18 00:00 (end of train), h ∈ {2, 4}; (3) n_pos / airings of p in the 11-20 schedule × airings of p in the 21-30 schedule | as specified | — |
| D25 | ALS (b): implicit 0.7.3 `AlternatingLeastSquares(iterations=15, random_state=42)`, CPU, `OPENBLAS_NUM_THREADS=1`; matrix = warm train users × programmes with ≥ 1 train positive, value = n_pos or log1p(n_pos); implicit multiplies values by `alpha` (Cui = alpha·r). Score = user·item factors over pool items that have factors (train items in the pool); no filtering of history | as specified; pool programmes without train positives have no factors and can only come from the fallback | — |
| D26 | PPR (c): nodes = warm train users + train programmes; edge weight = n_pos; transition P = row-normalised adjacency; update x' = α·Pᵀx + (α·dangling mass + 1−α)·e_u, with **α = probability of following an edge** (restart 1−α at the user). Per-user L1 residual, converged when < 1e-6, cap 200, converged columns frozen. Users in chunks of 1,000. Item score = stationary mass on the item node; only items with mass > 0 are ranked | as specified; α read as the damping factor (0.85 = classic PageRank) | α as restart probability would flip the grid |
| D27 | Content (d): tokens per programme = category, genres 1–3, every channel it airs on, each director and each actor (comma-split); token sets are unioned over all airings in the 11-20 and 21-30 schedules (metadata of what airs, not who watched). Binary tf × smooth idf `log((1+N)/(1+df))+1`, L2-normalised rows; profile = n_pos-weighted mean of train item vectors; score = cosine. Implemented with scipy (sklearn not installed) | as specified | year_of_production and title words not used |
| D28 | Airing variant (e): score × log1p(#airings of the programme in the 21-30 schedule), applied to the raw method score. For ALS, negative scores become more negative, which is accepted as specified | Kaggle counts airings (B14) | — |
