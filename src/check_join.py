"""Brute-force check of join.overlap_pairs on a sample (cartesian merge is OK at this size).
Run: .venv/bin/python src/check_join.py
"""
import numpy as np
import pandas as pd

from join import build_airings, overlap_pairs, secs
from load import load_log


def main():
    rng = np.random.default_rng(42)
    log, a = load_log(), build_airings()
    # random channels + channels known to contain overlapping airings (282, 487) or schedule gaps (1528)
    chs = rng.choice(log.vsetv_id.unique(), 6, replace=False).tolist() + [282, 487, 1528]
    lg = log[log.vsetv_id.isin(chs) & (log.start_time < "2020-06-08")].reset_index(drop=True)
    ag = a[a.channel_id.isin(chs) & (a.start_time < "2020-06-10") & (a.duration > 0)]
    fast = overlap_pairs(lg, ag).sort_values(["view_row", "airing_id"]).reset_index(drop=True)
    m = lg.reset_index().rename(columns={"index": "view_row"}).merge(ag, left_on="vsetv_id", right_on="channel_id")
    ov = np.minimum(secs(m.stop_time), m.end_s.values) - np.maximum(secs(m.start_time_x), m.start_s.values)
    brute = (pd.DataFrame({"view_row": m.view_row, "airing_id": m.airing_id, "overlap_s": ov})[ov > 0]
             .sort_values(["view_row", "airing_id"]).reset_index(drop=True).astype(fast.dtypes.to_dict()))
    print(f"channels={chs} views={len(lg)} airings={len(ag)} fast_pairs={len(fast)} brute_pairs={len(brute)} "
          f"identical={fast.equals(brute)}")


if __name__ == "__main__":
    main()
