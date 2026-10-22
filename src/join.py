"""Join view log to schedule airings by channel + interval overlap (no cartesian merge).

Outputs (artifacts/):
  airings.parquet       all schedule rows (3 files concatenated), airing_id = global row id
  interactions.parquet  one row per (user, labelled airing): overlap_s, duration, screen_time
  unlab_seconds.parquet per (user, channel, period) seconds watched on tv_show_id == 0 airtime
Run: .venv/bin/python src/join.py
"""
import sys

import numpy as np
import pandas as pd

from load import ART, SCHED_FILES, load_log, load_sched

K = np.int64(10**11)  # channel offset; epoch seconds ~1.6e9 << K


def secs(x):
    return x.values.astype("datetime64[s]").astype(np.int64)


def build_airings():
    parts = []
    for p, f in SCHED_FILES.items():
        s = load_sched(p)
        s["src_row"] = np.arange(len(s))  # 0-based data row in its csv (csv line = src_row + 2)
        s["src_file"] = f
        parts.append(s)
    a = pd.concat(parts, ignore_index=True)
    a["airing_id"] = np.arange(len(a), dtype=np.int64)
    a["start_s"] = secs(a.start_time)
    a["end_s"] = a.start_s + a.duration
    return a


def overlap_pairs(log, a):
    """All (view, airing) pairs on the same channel with overlap > 0."""
    a = a[a.duration > 0].sort_values(["channel_id", "start_s"])
    a_ch = a.channel_id.values.astype(np.int64) * K
    a_start = a_ch + a.start_s.values
    a_end_cummax = np.maximum.accumulate(a_ch + a.end_s.values)
    v_ch = log.vsetv_id.values.astype(np.int64) * K
    v_start = v_ch + secs(log.start_time)
    v_stop = v_ch + secs(log.stop_time)
    lo = np.searchsorted(a_end_cummax, v_start, side="right")  # first airing whose (cummax) end > view start
    hi = np.searchsorted(a_start, v_stop, side="left")         # airings starting before view stop
    n = np.clip(hi - lo, 0, None)
    vi = np.repeat(np.arange(len(log)), n)
    ai = np.repeat(lo, n) + (np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n))
    ov_end = np.minimum(v_stop[vi], a_ch[ai] + a.end_s.values[ai])
    ov_start = np.maximum(v_start[vi], a_start[ai])
    ov = ov_end - ov_start
    keep = ov > 0
    return pd.DataFrame({
        "view_row": vi[keep],
        "airing_id": a.airing_id.values[ai[keep]],
        "overlap_s": ov[keep],
        "ov_start": ov_start[keep] % K,  # clipped piece [ov_start, ov_end) in epoch seconds
        "ov_end": ov_end[keep] % K,
    })


def union_seconds(user, airing, st, en):
    """Per (user, airing): length of the union of pieces [st, en). Returns (keys frame, union_s)."""
    d = pd.DataFrame({"u": user, "a": airing, "st": st, "en": en}).sort_values(["u", "a", "st"], kind="stable")
    new = (d.u.ne(d.u.shift()) | d.a.ne(d.a.shift())).values
    g = np.cumsum(new)
    # running max of earlier ends inside the group (reset at group start)
    prev = d.en.groupby(g).cummax().groupby(g).shift().fillna(-1).astype(np.int64).values
    contrib = np.maximum(0, d.en.values - np.maximum(d.st.values, prev))
    return pd.DataFrame({"user_id": d.u.values[new], "airing_id": d.a.values[new],
                         "union_s": np.bincount(g - 1, weights=contrib).astype(np.int64)})


def main():
    log = load_log()
    log["view_row"] = np.arange(len(log))  # 0-based data row in dataset11-30.csv
    n_raw = len(log)
    log = log[~log.duplicated(["user_id", "vsetv_id", "start_time", "stop_time", "duration"])]
    print(f"log rows raw={n_raw} after exact-dup drop={len(log)} (dropped {n_raw - len(log)})")

    a = build_airings()
    a.drop(columns=["start_s", "end_s"]).to_parquet(ART / "airings.parquet", index=False)
    pairs = overlap_pairs(log.reset_index(drop=True), a)
    # pairs.view_row is positional in the deduped log -> map back to raw csv row
    pairs["view_row"] = log.view_row.values[pairs.view_row.values]
    pairs["user_id"] = load_log().user_id.values[pairs.view_row.values]
    meta = a.set_index("airing_id")[["tv_show_id", "channel_id", "period", "start_time", "duration"]]
    pairs = pairs.join(meta, on="airing_id")
    pairs.to_parquet(ART / "view_airing_pairs.parquet", index=False)

    covered = pairs.groupby("view_row").overlap_s.sum()
    vdur = load_log().duration.values
    print(f"(view, airing) pairs with overlap>0: {len(pairs)}; views with >=1 airing: {covered.size} of {len(log)}; "
          f"view seconds covered by any airing: {covered.sum() / vdur[log.view_row.values].sum():.4%}")

    lab = pairs[pairs.tv_show_id != 0]
    inter = (lab.groupby(["user_id", "airing_id"])
             .agg(overlap_sum_s=("overlap_s", "sum"), n_pieces=("overlap_s", "size"),
                  tv_show_id=("tv_show_id", "first"), channel_id=("channel_id", "first"),
                  period=("period", "first"), airing_start=("start_time", "first"),
                  duration=("duration", "first"))
             .reset_index())
    uni = union_seconds(lab.user_id.values, lab.airing_id.values, lab.ov_start.values, lab.ov_end.values)
    inter = inter.merge(uni, on=["user_id", "airing_id"], how="left", validate="1:1")
    # DESIGN D11 (revised): screen time = union of the user's pieces / duration, clipped to 1
    inter["overlap_s"] = inter.union_s
    inter["screen_time"] = np.minimum(1.0, inter.overlap_s / inter.duration)
    inter["screen_time_sum"] = inter.overlap_sum_s / inter.duration
    print(f"union > duration (clip active): {(inter.overlap_s > inter.duration).sum()}; "
          f"union != sum: {(inter.overlap_s != inter.overlap_sum_s).sum()}")
    inter.to_parquet(ART / "interactions.parquet", index=False)

    unlab = (pairs[pairs.tv_show_id == 0]
             .groupby(["user_id", "channel_id", "period"]).overlap_s.sum()
             .rename("seconds").reset_index())
    unlab.to_parquet(ART / "unlab_seconds.parquet", index=False)
    print(f"interactions (user, labelled airing): {len(inter)}; unlabelled (user, channel, period) rows: {len(unlab)}")


if __name__ == "__main__":
    sys.exit(main())
