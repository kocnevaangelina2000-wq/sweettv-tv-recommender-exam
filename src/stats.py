"""Post-join stats: test-user coverage, screen-time distribution, accounting, hand-check rows.
Run after src/join.py: .venv/bin/python src/stats.py
"""
import numpy as np
import pandas as pd

from load import DATA, LOG_FILE, SCHED_FILES, load_log, load_sched, load_sub, ART

THR = 0.8
SEED = 42


def raw_lines(path, line_nos):
    """Return {line_no: raw text} for 1-based line numbers (file has no embedded newlines: rows == lines-1)."""
    want, out = set(line_nos), {}
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if i in want:
                out[i] = line.rstrip("\n")
                if len(out) == len(want):
                    break
    return out


def main():
    log = load_log()
    sub = load_sub()
    test = set(sub.user_id)
    inter = pd.read_parquet(ART / "interactions.parquet")
    pairs = pd.read_parquet(ART / "view_airing_pairs.parquet")
    airings = pd.read_parquet(ART / "airings.parquet")
    pos = inter[inter.screen_time >= THR]

    print("== VIEWS WITH NO AIRING")
    sched_ch = set(airings.channel_id)
    unmatched = np.setdiff1d(np.arange(len(log)), pairs.view_row.unique())
    um = log.iloc[unmatched]
    print(f"views (raw rows, incl. 17 exact dups) with no overlapping airing: {len(um)}; on channels absent from schedule: "
          f"{(~um.vsetv_id.isin(sched_ch)).sum()}; on scheduled channels: {um.vsetv_id.isin(sched_ch).sum()} "
          f"(top channels: {um[um.vsetv_id.isin(sched_ch)].vsetv_id.value_counts().head(5).to_dict()})")

    print("== TEST USERS (submission.csv)")
    print(f"test users={len(test)} unique={sub.user_id.nunique()}")
    in_log = test & set(log.user_id)
    lab_users = set(inter.user_id)
    print(f"with any view in 11-30: {len(in_log)}; with a labelled view (overlap>0 with tv_show_id!=0 airing): "
          f"{len(test & lab_users)}; with >=1 airing at screen_time>={THR}: {len(test & set(pos.user_id))}")
    for p in ["11-20", "21-30"]:
        print(f"   in period {p}: any view {len(test & set(pairs[pairs.period == p].user_id))}, labelled "
              f"{len(test & set(inter[inter.period == p].user_id))}, >=0.8 {len(test & set(pos[pos.period == p].user_id))}")

    print("== SCREEN TIME (one row per user x labelled airing)")
    q = [.01, .05, .1, .25, .5, .75, .9, .95, .99]
    print("percentiles:", inter.screen_time.quantile(q).round(4).to_dict(), "max:", round(inter.screen_time.max(), 3))
    print(f"share >= {THR}: {(inter.screen_time >= THR).mean():.4%}; share > 1: {(inter.screen_time > 1).mean():.4%} "
          f"({(inter.screen_time > 1).sum()} rows; of those with n_pieces>1: {((inter.screen_time > 1) & (inter.n_pieces > 1)).sum()}); "
          f"rows with n_pieces>1: {(inter.n_pieces > 1).sum()}")
    for p in ["11-20", "21-30"]:
        x = inter[inter.period == p]
        print(f"   {p}: rows={len(x)} p50={x.screen_time.median():.4f} share>=0.8={(x.screen_time >= THR).mean():.4%}")

    print("== (user, programme) PAIRS WITH >=1 AIRING AT >= 0.8")
    cnt = pos.groupby(["period", "user_id", "tv_show_id"]).size().rename("n").reset_index()
    for p in ["11-20", "21-30"]:
        c = cnt[cnt.period == p]
        print(f"   {p}: pairs={len(c)} users={c.user_id.nunique()} programmes={c.tv_show_id.nunique()} "
              f"airings-per-pair mean={c.n.mean():.3f}")
    c = cnt[(cnt.period == "21-30") & cnt.user_id.isin(test)]
    per_user = c.groupby("user_id").size().reindex(sorted(test), fill_value=0)
    print(f"test users by #programmes>=0.8 in 21-30: >=5: {(per_user >= 5).sum()}, 1-4: {((per_user >= 1) & (per_user <= 4)).sum()}, "
          f"0: {(per_user == 0).sum()}")
    # ties at the 5th place under the Kaggle rule (count desc) among users with >=5 programmes
    ties = 0
    for u, g in c.groupby("user_id"):
        if len(g) >= 5:
            n = np.sort(g.n.values)[::-1]
            ties += len(n) > 5 and n[4] == n[5]
    print(f"test users with >=5 programmes whose 5th and 6th counts tie in 21-30: {ties}")

    print("== ACCOUNTING")
    rows = []
    rows.append(("raw rows dataset11-30.csv", len(log)))
    for p in SCHED_FILES:
        s = load_sched(p)
        rows.append((f"raw rows schedule {p}", len(s)))
        rows.append((f"labelled rows (tv_show_id!=0) schedule {p}", int((s.tv_show_id != 0).sum())))
        rows.append((f"distinct labelled programmes schedule {p}", s.tv_show_id[s.tv_show_id != 0].nunique()))
    rows.append(("log rows after exact-dup drop", len(log) - int(log.duplicated().sum())))
    rows.append(("(view, airing) pairs overlap>0, any airing", len(pairs)))
    for p in ["11-20", "21-30"]:
        x, y = inter[inter.period == p], pos[pos.period == p]
        rows += [(f"joined interactions (user, labelled airing) {p}", len(x)),
                 (f"interactions screen_time>=0.8 {p}", len(y)),
                 (f"users with interactions {p}", x.user_id.nunique()),
                 (f"users with >=0.8 interaction {p}", y.user_id.nunique()),
                 (f"programmes with interactions {p}", x.tv_show_id.nunique()),
                 (f"programmes with >=0.8 interaction {p}", y.tv_show_id.nunique())]
    rows.append(("users in log", log.user_id.nunique()))
    rows.append(("test users", len(test)))
    rows.append(("cold test users: no view in 11-30", len(test - set(log.user_id))))
    rows.append(("cold test users: no labelled interaction in 11-30", len(test - lab_users)))
    rows.append(("cold test users: no >=0.8 interaction in 11-30", len(test - set(pos.user_id))))
    rows.append(("cold test users: no >=0.8 interaction in 21-30", len(test - set(pos[pos.period == "21-30"].user_id))))
    for k, v in rows:
        print(f"| {k} | {v} |")

    print("== 3 RANDOM JOINED ROWS (seed 42)")
    rng = np.random.default_rng(SEED)
    pick = inter.iloc[rng.choice(len(inter), 3, replace=False)]
    for _, r in pick.iterrows():
        a = airings.loc[airings.airing_id == r.airing_id].iloc[0]
        pv = pairs[(pairs.user_id == r.user_id) & (pairs.airing_id == r.airing_id)].sort_values("view_row")
        sl = raw_lines(DATA / a.src_file, [a.src_row + 2])
        ll = raw_lines(DATA / LOG_FILE, (pv.view_row + 2).tolist())
        print(f"\n--- interaction: user_id={r.user_id} airing_id={r.airing_id} tv_show_id={r.tv_show_id} period={r.period} "
              f"overlap_s={r.overlap_s} n_pieces={r.n_pieces} duration={r.duration} screen_time={r.screen_time:.4f}")
        print(f"schedule {a.src_file} line {a.src_row + 2}:\n  {sl[a.src_row + 2]}")
        end = a.start_time + pd.Timedelta(seconds=int(a.duration))
        print(f"  airing interval [{a.start_time}, {end})")
        for _, v in pv.iterrows():
            print(f"log {LOG_FILE} line {v.view_row + 2}:\n  {ll[v.view_row + 2]}\n  -> overlap_s={v.overlap_s}")


if __name__ == "__main__":
    main()
