"""Brute-force check of join.overlap_pairs on a sample (cartesian merge is OK at this size).
Run: .venv/bin/python src/check_join.py
"""
import numpy as np
import pandas as pd

from join import build_airings, overlap_pairs, secs, union_seconds
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
    en = np.minimum(secs(m.stop_time), m.end_s.values)
    st = np.maximum(secs(m.start_time_x), m.start_s.values)
    ov = en - st
    brute = (pd.DataFrame({"view_row": m.view_row, "airing_id": m.airing_id, "overlap_s": ov,
                           "ov_start": st, "ov_end": en})[ov > 0]
             .sort_values(["view_row", "airing_id"]).reset_index(drop=True).astype(fast.dtypes.to_dict()))
    print(f"channels={chs} views={len(lg)} airings={len(ag)} fast_pairs={len(fast)} brute_pairs={len(brute)} "
          f"identical={fast.equals(brute)}")
    # union: naive per-group interval merge vs vectorised union_seconds
    fast["user_id"] = lg.user_id.values[fast.view_row.values]
    naive = {}
    for (u, a_), g in fast.groupby(["user_id", "airing_id"]):
        tot, cur_s, cur_e = 0, None, None
        for s_, e_ in sorted(zip(g.ov_start, g.ov_end)):
            if cur_e is None or s_ > cur_e:
                tot += 0 if cur_e is None else cur_e - cur_s
                cur_s, cur_e = s_, e_
            else:
                cur_e = max(cur_e, e_)
        naive[(u, a_)] = tot + (cur_e - cur_s)
    vec = union_seconds(fast.user_id.values, fast.airing_id.values, fast.ov_start.values, fast.ov_end.values)
    vec_d = dict(zip(zip(vec.user_id, vec.airing_id), vec.union_s))
    multi = (fast.groupby(["user_id", "airing_id"]).size() > 1).sum()
    print(f"union check: groups={len(naive)} (with >1 piece: {multi}) vectorised==naive: {vec_d == naive}")


if __name__ == "__main__":
    main()
