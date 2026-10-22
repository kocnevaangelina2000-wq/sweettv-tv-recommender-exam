"""Follow-up checks on traps found by audit.py / stats.py. Run after src/join.py:
.venv/bin/python src/extra_checks.py
"""
import numpy as np
import pandas as pd

from load import ART, SCHED_FILES, load_log, load_sched, load_sub

DST = pd.Timestamp("2020-03-29 03:00:00")  # Europe/Kyiv EET->EEST, wall clock jumps 03:00 -> 04:00


def secs(x):
    return np.asarray(x).astype("datetime64[s]").astype(np.int64)


def main():
    log = load_log()
    test = set(load_sub().user_id)

    print("== DST (log)")
    bad = (log.stop_time - log.start_time).dt.total_seconds() != log.duration
    span = (log.start_time <= DST) & (log.stop_time > DST)
    print(f"duraton != stop-start: {bad.sum()}; spanning {DST}: {span.sum()}; both: {(bad & span).sum()}; "
          f"views starting in the skipped hour [03:00,04:00): {((log.start_time >= DST) & (log.start_time < DST + pd.Timedelta(hours=1))).sum()}")

    print("== DST (schedule 11-20)")
    s = load_sched("11-20").sort_values(["channel_id", "start_time"])
    gap = (s.groupby("channel_id").start_time.shift(-1) - s.start_time).dt.total_seconds()
    mis = gap.notna() & (gap != s.duration)
    sp = (s.start_time < DST) & (s.start_time + pd.to_timedelta(s.duration, unit="s") > DST)
    print(f"duration != gap-to-next: {mis.sum()}; airings spanning {DST}: {sp.sum()}; both: {(mis & sp).sum()}; "
          f"(gap - duration) on those: {(gap - s.duration)[mis & sp].value_counts().to_dict()}; "
          f"airings starting in skipped hour: {((s.start_time >= DST) & (s.start_time < DST + pd.Timedelta(hours=1))).sum()}")

    print("== WEEKLY VOLUME (log, ISO week of start)")
    wk = log.start_time.dt.isocalendar().week
    t = pd.DataFrame({"rows": wk.value_counts().sort_index(),
                      "users": log.groupby(wk).user_id.nunique(),
                      "test_users": log[log.user_id.isin(test)].groupby(wk).user_id.nunique()})
    print(t.T.to_string())
    u_early, u_late = set(log.user_id[wk <= 27]), set(log.user_id[wk >= 28])
    print(f"users seen only in weeks 28-30: {len(u_late - u_early)}; test users among them: {len(test & (u_late - u_early))}")

    print("== SCHEDULE COVERAGE OF CHANNELS WITH MOST UNMATCHED VIEWS")
    A = pd.read_parquet(ART / "airings.parquet")
    pairs = pd.read_parquet(ART / "view_airing_pairs.parquet")
    um = log.iloc[np.setdiff1d(np.arange(len(log)), pairs.view_row.unique())]
    for ch in um[um.vsetv_id.isin(A.channel_id)].vsetv_id.value_counts().index[:5]:
        a = A[A.channel_id == ch]
        u = um[um.vsetv_id == ch]
        print(f"ch {ch} {a.channel_title.iloc[0]}: first airing {a.start_time.min()}; unmatched views {len(u)}, "
              f"of which before first airing: {(u.stop_time <= a.start_time.min()).sum()}")

    print("== SCREEN TIME: SUM vs UNION of a user's overlapping pieces")
    P = pairs[pairs.tv_show_id != 0]
    Ai = A.set_index("airing_id")
    ast = secs(Ai.start_time.loc[P.airing_id].values)
    dur = Ai.duration.loc[P.airing_id].values
    d = pd.DataFrame({"u": P.user_id.values, "a": P.airing_id.values,
                      "st": np.maximum(secs(log.start_time.values[P.view_row.values]), ast),
                      "en": np.minimum(secs(log.stop_time.values[P.view_row.values]), ast + dur), "dur": dur})
    d = d.sort_values(["u", "a", "st"]).reset_index(drop=True)
    g = (d.u.ne(d.u.shift()) | d.a.ne(d.a.shift())).cumsum()
    prev = d.groupby(g).en.cummax().groupby(g).shift().fillna(-1).astype(np.int64)
    d["uni"] = np.maximum(0, d.en - np.maximum(d.st, prev))
    d["sm"] = d.en - d.st
    agg = d.groupby(g).agg(sm=("sm", "sum"), uni=("uni", "sum"), dur=("dur", "first"))
    s_sum, s_uni = agg.sm / agg.dur, agg.uni / agg.dur
    print(f"interactions={len(agg)}; sum != union: {(agg.sm != agg.uni).sum()}; max union screen time: {s_uni.max():.4f}; "
          f">=0.8 by sum: {(s_sum >= .8).sum()}, by union: {(s_uni >= .8).sum()}, sum-only: {((s_sum >= .8) & (s_uni < .8)).sum()}")
    l = log.sort_values(["user_id", "vsetv_id", "start_time"])
    ov = l.user_id.eq(l.user_id.shift()) & l.vsetv_id.eq(l.vsetv_id.shift()) & (l.start_time < l.stop_time.shift())
    print(f"same-user same-channel overlapping views: {ov.sum()} across {l.user_id[ov].nunique()} users")


if __name__ == "__main__":
    main()
