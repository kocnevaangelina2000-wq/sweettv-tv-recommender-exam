# sweet.tv TV-programme recommender — exam repository

Repository: https://github.com/kocnevaangelina2000-wq/sweettv-tv-recommender-exam

A Top-5 TV-programme recommender for the Kaggle competition [sweet.tv - TV program recommender](https://www.kaggle.com/competitions/sweettv-tv-program-recommender), scored by MAP@5 over 1,260 test users. Training uses weeks 11–30 of 2020; the predictions are for weeks 31–42.

**Final submission: [`submissions/s8_blend.csv`](submissions/s8_blend.csv)**, Kaggle private 0.44568 / public 0.44710. It is the file with the best private score among those submitted. That is the instructor's grading rule, and it means the file was chosen *by* the private score. All scores are in `RESULTS.md` (section "Kaggle scores — complete").

| file | content |
|---|---|
| `RESULTS.md` | every number, with the command that produced it |
| `DESIGN.md` | every decision (D1–D70) and why |
| `BUGLOG.md` | every bug and data trap (B1–B42) |
| `PROVENANCE.md` | raw-data checksums and row counts |
| `report/report.md`, `report/report.pdf` | the exam report (IEEE structure; build: `PYTHONPATH=<dir with markdown 3.7> /usr/bin/python3 report/build_pdf.py`, needs Google Chrome) |
| `AI_NOTES.md` | how the AI assistant was used |
| `src/` | all code; `tests/` metric unit tests; `logs/` outputs of every run |
| `submissions/` | every written submission file (s1–s10, including the unsubmitted s2, s2b, s4, s5) |
| `analysis/` | hand-check pack and reference records (`analysis/refs/`). The two hand-check CSVs with raw log/schedule rows (`hand_check_a_*.csv`) are **not published**, because the competition data is not ours to redistribute. Regenerate them with `.venv/bin/python src/hand_check.py` from the Kaggle data. For the same reason, the raw rows in `logs/stats.log` are replaced by a pointer (DESIGN D70) |

## Environment
| item | version |
|---|---|
| hardware / OS | Apple M3 Max (14 cores, 36 GB), macOS 26.6.2 |
| Python | 3.9.6 (`/usr/bin/python3`), venv `.venv` created with `--system-site-packages` |
| numpy / scipy | 2.0.2 / 1.13.1 |
| pandas / pyarrow | 2.2.3 / 17.0.0 |
| scikit-learn | 1.5.2 (HistGradientBoostingRegressor, GroupKFold) |
| implicit | 0.7.3 (ALS, BM25 weighting) |
| catboost | 1.2.8 (CatBoostRanker, YetiRank), installed with `--no-deps` so that numpy stays at 2.0.2 (BUGLOG B34) |

All randomness is seeded with 42; seed bagging uses seeds 42–46. Entry scripts set `OPENBLAS_NUM_THREADS=1` before importing numpy (BUGLOG B24).

```
/usr/bin/python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install --no-deps catboost==1.2.8
```

## Data
The competition data is not in this repository. Put the five files in `data/`: `dataset11-30.csv`, `export_arh_11-20-final.csv`, `export_arh_21-30-final.csv`, `export_arh_31-42-final.csv` and `submission.csv`. Check them against the sha256 sums in `PROVENANCE.md`. Parsed caches are written to `artifacts/`, which is not tracked.

## Reproduce end to end (from the repo root, in this order)
Runtimes are the wall times measured on the machine above (`/usr/bin/time -p`, or as logged); "—" = not measured.

| # | command | writes | wall time |
|---|---|---|---|
| 1 | `.venv/bin/python src/join.py > logs/join.log` | `artifacts/` (airings, interactions, view–airing pairs) | — |
| 2 | `.venv/bin/python src/audit.py > logs/audit.log`; `src/extra_checks.py`; `src/stats.py`; `src/check_join.py` | data audit, accounting, join checks | — |
| 3 | `.venv/bin/python -m unittest discover -s tests -v` | metric tests | < 1 s |
| 4 | `.venv/bin/python src/s1_popularity.py > logs/s1_popularity.log` | `submissions/s1_popularity.csv` | — |
| 5 | `.venv/bin/python src/s4a_folds.py > logs/s4a_folds.log` | folds A/B grids, `logs/s4a_selected.json`, `s2_history.csv`, `s3_ppr_air.csv` | 748 s |
| 6 | `.venv/bin/python src/check_history_ties.py`; `src/s2b_history.py > logs/s2b_history.log` | tie-break check, `s2b_history.csv` | — |
| 7 | `.venv/bin/python src/s4b_hybrids.py > logs/s4b_hybrids.log`; `src/check_hgb_stopping.py` | H1/H2/H3, `s4_h1.csv`, `s5_best_hybrid.csv` | 352 s |
| 8 | `.venv/bin/python src/check_title_transfer.py`; `src/s4c_h3plus.py > logs/s4c_h3plus.log` | H3+, ablation, `s6_h3plus.csv` | 367 s |
| 9 | `.venv/bin/python src/s5_push.py > logs/s5_push.log` | step-5 table, `logs/s5_rows.csv`, `s7_best.csv` | 3,931 s |
| 10 | `.venv/bin/python src/s5_blend.py > logs/s5_blend.log` (needs the logs of 5, 7 and 9) | blend grid, **`s8_blend.csv` (final)** | 843 s |
| 11 | `.venv/bin/python src/s7b_perweek.py > logs/s7b_perweek.log` | `s7b_perweek.csv` | 527 s |
| 12 | `.venv/bin/python src/s9_blend_pw.py > logs/s9_blend_pw.log` | `s9_blend_pw.csv` | 1,349 s |
| 13 | `.venv/bin/python src/s10_blend_abc.py > logs/s10_blend_abc.log` | folds B/C table, `s10_blend_abc.csv` | 4,493 s |
| 14 | `.venv/bin/python src/examples.py > logs/examples.log`; `src/hand_check.py` | report examples (`logs/examples.md`), hand-check pack | — |

Only steps 1–10 are needed for the final file. Each writer validates its submission (header, 1,260 rows, template order, 5 unique ids, all ids in the 31–42 pool) and prints the result.
