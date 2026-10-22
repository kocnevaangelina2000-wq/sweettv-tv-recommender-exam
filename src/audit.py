"""Step-3 audit of raw files (pre-join). Run: .venv/bin/python src/audit.py"""
import numpy as np
import pandas as pd

from load import SCHED_FILES, load_log, load_sched

K = np.int64(10**11)


def secs(x):
    return x.values.astype("datetime64[s]").astype(np.int64)


def iso_weeks(ts):
    w = ts.dt.isocalendar().week
    return f"ISO weeks {w.min()}..{w.max()} ({w.nunique()} distinct)"


def audit_log(log):
    print("== LOG dataset11-30.csv")
    print(f"rows={len(log)} users={log.user_id.nunique()} channels={log.vsetv_id.nunique()} "
          f"user_id max={log.user_id.max()} (> int64 max: {(log.user_id > np.iinfo(np.int64).max).sum()} rows)")
    print(f"start_time {log.start_time.min()} ({log.start_time.min().day_name()}) .. {log.start_time.max()}; "
          f"stop_time {log.stop_time.min()} .. {log.stop_time.max()} ({log.stop_time.max().day_name()}); {iso_weeks(log.start_time)}")
    d = (log.stop_time - log.start_time).dt.total_seconds()
    bad = d != log.duration
    print(f"duraton == stop-start: {(~bad).sum()} / {len(log)}; mismatches={bad.sum()}, "
          f"diff (duraton - (stop-start)) values: {(log.duration - d)[bad].value_counts().head(5).to_dict()}")
    print(f"duraton min={log.duration.min()} p50={log.duration.median()} p99={log.duration.quantile(.99)} max={log.duration.max()}; "
          f"> 24h: {(log.duration > 86400).sum()}; < 60s: {(log.duration < 60).sum()}")
    print(f"exact duplicate rows: {log.duplicated().sum()}")
    l = log.sort_values(["user_id", "start_time"])
    same = l.user_id.eq(l.user_id.shift())
    ov = same & (l.start_time < l.stop_time.shift())
    print(f"views overlapping the same user's previous view (any channel): {ov.sum()} ({ov.mean():.4%})")
    wk = log.start_time.dt.isocalendar().week
    print("rows per ISO week:", wk.value_counts().sort_index().to_dict())


def audit_sched(S):
    for p, s in S.items():
        print(f"== SCHEDULE {p} ({SCHED_FILES[p]})")
        end = s.start_time + pd.to_timedelta(s.duration, unit="s")
        print(f"rows={len(s)} channels={s.channel_id.nunique()} start {s.start_time.min()} ({s.start_time.min().day_name()}) "
              f".. {s.start_time.max()}; max end {end.max()}; {iso_weeks(s.start_time)}")
        rows_by_wk = s.start_time.dt.isocalendar().week.value_counts().sort_index()
        print(f"rows per ISO week: {rows_by_wk.to_dict()}")
        s2 = s.sort_values(["channel_id", "start_time"])
        gap = (s2.start_time.shift(-1) - s2.start_time).dt.total_seconds()
        samech = s2.channel_id.eq(s2.channel_id.shift(-1))
        print(f"duration: min={s.duration.min()} p50={s.duration.median()} max={s.duration.max()} all multiples of 60: "
              f"{(s.duration % 60 == 0).all()}; duration == seconds to next airing on channel: "
              f"{(gap[samech] == s2.duration[samech]).mean():.4%}")
        lab = s.tv_show_id != 0
        print(f"tv_show_id != 0: rows {lab.mean():.4%}, airtime {s.duration[lab].sum() / s.duration.sum():.4%}, "
              f"distinct labelled ids {s.tv_show_id[lab].nunique()}")
        e2 = s2.start_time + pd.to_timedelta(s2.duration, unit="s")
        ovl = samech & (s2.start_time.shift(-1) < e2)
        print(f"duplicate (channel,start): {s.duplicated(['channel_id', 'start_time']).sum()}; exact dup rows: "
              f"{s.drop(columns='period').duplicated().sum()}; duration==0: {(s.duration == 0).sum()}; "
              f"overlapping consecutive airings: {ovl.sum()}; gaps: {(samech & (s2.start_time.shift(-1) > e2)).sum()}")
        print(f"channel_id with >1 channel_title: {(s.groupby('channel_id').channel_title.nunique() > 1).sum()}")
    for a, b in [("11-20", "21-30"), ("21-30", "31-42")]:
        ea = (S[a].start_time + pd.to_timedelta(S[a].duration, unit="s")).groupby(S[a].channel_id).max()
        sb = S[b].groupby("channel_id").start_time.min()
        j = pd.concat([ea.rename("end_a"), sb.rename("start_b")], axis=1).dropna()
        print(f"tiling {a}->{b}: shared channels={len(j)}, last end of {a} == first start of {b}: {(j.end_a == j.start_b).sum()}; "
              f"mismatched: {j[j.end_a != j.start_b].to_dict('index')}")


def audit_tz(log, S):
    """If log and schedule share a clock, view starts cluster right after airing starts at shift 0."""
    print("== CLOCK ALIGNMENT (log vs schedule, same channel)")
    s = pd.concat(S.values())
    s = s[s.duration > 0]
    a_ch = s.channel_id.values.astype(np.int64) * K
    ast = np.unique(a_ch + secs(s.start_time))
    aen = np.unique(a_ch + secs(s.start_time) + s.duration.values)
    v_ch = log.vsetv_id.values.astype(np.int64) * K
    vs = np.sort(v_ch + secs(log.start_time))
    ve = np.sort(v_ch + secs(log.stop_time))

    def start_rate(q, sh):  # share of views starting within [0,60s) after an airing start shifted by sh
        q = q - sh
        return (np.searchsorted(ast, q, "right") - np.searchsorted(ast, q - 60, "right") > 0).mean()

    def stop_rate(q, sh):  # share of views stopping within [0,60s) before an airing end shifted by sh
        q = q - sh
        return (np.searchsorted(aen, q + 60, "left") - np.searchsorted(aen, q, "left") > 0).mean()

    shifts_min = sorted(set(range(-180, 181, 15)) | set(range(-5, 6)))
    for name, f, q in [("view start vs airing start", start_rate, vs), ("view stop vs airing end", stop_rate, ve)]:
        r = pd.Series({m: f(q, m * 60) for m in shifts_min})
        print(f"{name}: best shift={r.idxmax()} min (rate {r.max():.4f}); rate at 0={r[0]:.4f}; "
              f"at -5..+5 min={r.loc[-5:5].round(4).tolist()}; at ±60={r[-60]:.4f}/{r[60]:.4f}; "
              f"±120={r[-120]:.4f}/{r[120]:.4f}; ±180={r[-180]:.4f}/{r[180]:.4f}; median over shifts={r.median():.4f}")
    for name, m in [("before DST 2020-03-29", log.start_time < "2020-03-29"),
                    ("after DST", log.start_time >= "2020-03-30")]:
        q = np.sort(v_ch[m.values] + secs(log.start_time[m]))
        r = pd.Series({h: start_rate(q, h * 3600) for h in range(-3, 4)})
        print(f"{name}: view-start rate by whole-hour shift {r.round(4).to_dict()}")


def main():
    log = load_log()
    S = {p: load_sched(p) for p in SCHED_FILES}
    audit_log(log)
    print(f"log channels absent from all schedules: {sorted(set(log.vsetv_id) - set(pd.concat(S.values()).channel_id))}, "
          f"rows on them: {(~log.vsetv_id.isin(pd.concat(S.values()).channel_id)).sum()}")
    audit_sched(S)
    audit_tz(log, S)


if __name__ == "__main__":
    main()
