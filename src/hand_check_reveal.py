"""Run AFTER doing part a) by hand: prints the code's per-airing values for the hand-check user and programme
(airing csv line, union overlap seconds, screen time, positive flag, positive count).
Run: .venv/bin/python src/hand_check_reveal.py
"""
import pandas as pd

from load import ART, ROOT
from protocol import THR, load_interactions

A = ROOT / "analysis"
u = int(pd.read_csv(A / "hand_check_a_log_rows.csv", dtype=str).user_id.iloc[0])
s = pd.read_csv(A / "hand_check_a_schedule_rows.csv", dtype=str)
p = int(s.tv_show_id.iloc[0])
air = pd.read_parquet(ART / "airings.parquet", columns=["airing_id", "src_file", "src_row"])
inter = load_interactions()
t = inter[(inter.user_id == u) & (inter.tv_show_id == p) & (inter.period == "21-30")].merge(air, on="airing_id")
t["csv_line"] = t.src_row + 2
t["positive"] = t.screen_time >= THR
print(t[["csv_line", "airing_start", "duration", "n_pieces", "overlap_sum_s", "union_s", "screen_time", "positive"]]
      .sort_values("csv_line").to_string(index=False))
print(f"user {u}, programme {p}: positive count = {int(t.positive.sum())}; schedule csv lines in the pack == code "
      f"airings: {sorted(s.csv_line.astype(int)) == sorted(t.csv_line)}")
