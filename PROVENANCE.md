# PROVENANCE — raw data

All files are in `data/` (gitignored). Every file has mtime 2020-11-18.

| file | sha256 | bytes | lines (`wc -l`) | data rows (parsed) | columns |
|---|---|---|---|---|---|
| dataset11-30.csv | `8c9e5f058157041e5c33f13e64dc1625a5177cc6d5e434ba18cd8a69afafb53b` | 396216555 | 5821988 | 5821987 | user_id, vsetv_id, start_time, stop_time, duraton |
| export_arh_11-20-final.csv | `7888aa00c20db3db23f95000c721eccf2878e5f58bf5383bb25b99f078b1033c` | 153322643 | 1074236 | 1074235 | channel_id, channel_title, start_time, duration, tv_show_title, tv_show_id, tv_show_category, tv_show_genre_1, tv_show_genre_2, tv_show_genre_3, year_of_production, director, actors |
| export_arh_21-30-final.csv | `bdc9fa9850239aaed608bece9cdb200011e690300470fe85b980457d8c0cb2d4` | 154366907 | 1074395 | 1074394 | (same 13 as above) |
| export_arh_31-42-final.csv | `5cc01f4619bd94886d83744f00bbc15cc5fa23384d297244a7dc2207450c4088` | 185952991 | 1295379 | 1295378 | (same 13 as above) |
| submission.csv | `d8c209dce3c7c9d815d8e2a6226e1be63052ee7afa7e8ba8b75dc2f703967a02` | 38348 | 1260 | 1260 | user_id, tv_show_id |

Commands:
```
cd data && for f in *.csv; do echo "$f $(shasum -a 256 "$f" | cut -d' ' -f1) $(wc -l < "$f") $(stat -f %z "$f")"; done
.venv/bin/python -c "import pandas as pd; [print(f, pd.read_csv('data/'+f, dtype=str, keep_default_na=False).shape) for f in ['dataset11-30.csv','export_arh_11-20-final.csv','export_arh_21-30-final.csv','export_arh_31-42-final.csv','submission.csv']]"
```
Parsed rows = `wc -l` − 1 (header) for every file except submission.csv, which has no trailing newline, so its 1260 lines are 1 header + 1260 rows with the last line unterminated. Because the counts agree, no field contains an embedded newline, which is what lets the raw-line lookup in `src/stats.py` work.

submission.csv is the sample submission: 1260 unique test user_ids, all `tv_show_id = "0 0 0 0 0"` (5 space-separated ids).

Environment: `/usr/bin/python3` 3.9.6 → `.venv` (`--system-site-packages`): pandas 2.2.3, pyarrow 17.0.0, numpy 2.0.2, scipy 1.13.1, implicit 0.7.3.
