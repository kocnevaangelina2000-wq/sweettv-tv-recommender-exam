"""s10: the s9 config (DESIGN D64) with (1) a third training fold C (D65) and (2) recency features (D66).
SPECIFIED AFTER THE KAGGLE SCORES WERE KNOWN (BUGLOG B42); written regardless of the table below.
Evaluation: s9 config vs + recency, on B (fit on A) and on C (fit on A+B), cohort and test subset.
Final: fit on A+B+C stacked (label per target week), with recency, applied to 11-30 -> 31-42.
Run: .venv/bin/python src/s10_blend_abc.py -> logs/s10_blend_abc.log, submissions/s10_blend_abc.csv
"""
import os

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")  # before numpy/sklearn load BLAS (BUGLOG B24)

import time

import numpy as np
import pandas as pd

import s4b_hybrids as H
import s5_push as S5
import s9_blend_pw as S9  # imports s7b: "s7b per-week" feature set
from load import ART, load_sub
from protocol import THR, Split, load_interactions, load_unlab, mapk, window_mask
from s1_popularity import SUB_DIR, validate_submission, write_submission

S5.SplitData.ACTIVE_WEEKS = {"A": (11, 15), "B": (11, 20), "C": (11, 27), "final": (11, 30)}  # D62 + C
REC = ["rec_pos_pw", "rec_sec_pw", "weeks_since_pos"]
FEATS = {"s9 config": S9.FEATS, "+ recency": S9.FEATS + REC}
N_REC = 3


def add_recency(D, F, pairs):
    """Per (user, programme): positives and union seconds in the user's last N_REC active train weeks (nominal
    weeks, as for the active-week count), divided by the number of those weeks (<= 3); weeks from the last positive
    airing of the programme to the split's train end (NaN = no positive in train)."""
    sd = D.sd
    lo, hi = D.ACTIVE_WEEKS[sd.name]
    tw = pairs[window_mask(pairs, sd.train_windows) & pairs.user_id.isin(set(D.users)).values]
    aw = tw.loc[(tw.week >= lo) & (tw.week <= hi), ["user_id", "week"]].drop_duplicates()
    last = aw.sort_values(["user_id", "week"], ascending=[True, False]).groupby("user_id").head(N_REC)
    n_last = last.groupby("user_id").size()
    tr = sd.tr.merge(last, on=["user_id", "week"])  # train airings in the user's last N_REC active weeks
    g = tr.assign(pos=(tr.screen_time >= THR).astype(int)).groupby(["user_id", "tv_show_id"])
    rec = g.agg(rp=("pos", "sum"), rs=("overlap_s", "sum"))
    idx = pd.MultiIndex.from_frame(F[["user_id", "tv_show_id"]])
    nl = F.user_id.map(n_last).fillna(1).values
    F["rec_pos_pw"] = rec.rp.reindex(idx).fillna(0).values / nl
    F["rec_sec_pw"] = rec.rs.reindex(idx).fillna(0).values / nl
    lp = sd.pos.groupby(["user_id", "tv_show_id"]).week.max()
    F["weeks_since_pos"] = sd.train_end_week - lp.reindex(idx).values
    return F


def lists_for(F, sd, Ftr, feats, w, k):
    S9.FEATS = feats  # S9.blended reads its module-level feature list
    return S9.blended(F, sd, Ftr, Ftr.label_pw.values, w, k)


def main():
    t0 = time.perf_counter()
    inter, unlab = load_interactions(), load_unlab()
    test_list = load_sub().user_id.tolist()
    test = set(test_list)
    pairs = pd.read_parquet(ART / "view_airing_pairs.parquet",
                            columns=["user_id", "channel_id", "period", "week", "ov_start", "ov_end"])
    w, k = S9.blend_params()
    print(f"blend w(hgb, cb, h2)={w} k={k}; candidates: {S9.VARIANT}; recency features: {REC}", flush=True)
    D = {n: S5.SplitData(n, inter, unlab, pairs) for n in ["A", "B", "C"]}
    F = {}
    for n, d in D.items():
        F[n], _, _ = d.frame(S9.VARIANT, pairs)
        add_recency(d, F[n], pairs)
    sc = D["C"].sd
    ct = [u for u in sc.cohort if u in test]
    print(f"[C] cohort={len(sc.cohort)} (test users {len(ct)}); cohort users with >= 1 positive in the C train "
          f"window={sum(u in sc.hist for u in sc.cohort)} (test {sum(u in sc.hist for u in ct)}); warm users "
          f"(any positive in train)={len(sc.warm)}; pool={len(sc.pool)}; truth items={sum(map(len, sc.truth.values()))}",
          flush=True)
    for n in ["A", "B", "C"]:
        f = F[n]
        print(f"[{n}] frame rows={len(f)}; recency: rec_pos_pw>0 share={(f.rec_pos_pw > 0).mean():.3f}, "
              f"weeks_since_pos NaN share={f.weeks_since_pos.isna().mean():.3f}, "
              f"weeks_since_pos min={f.weeks_since_pos.min()} max={f.weeks_since_pos.max()}", flush=True)

    rows = []
    evals = [("B", F["A"]), ("C", pd.concat([F["A"], F["B"]], ignore_index=True))]
    for cfg, feats in FEATS.items():
        for n, Ftr in evals:
            t = time.perf_counter()
            sd = D[n].sd
            l = H.score_lists(sd, lists_for(F[n], sd, Ftr, feats, w, k), sd.cohort)
            ctn = [u for u in sd.cohort if u in test]
            r = {"config": cfg, "fold": n, "fit on": "A" if n == "B" else "A+B", "cohort": mapk(l, sd.truth, sd.cohort),
                 "test": mapk(l, sd.truth, ctn), "n_cohort": len(sd.cohort), "n_test": len(ctn),
                 "s": time.perf_counter() - t}
            rows.append(r)
            print(f"  {cfg} | {n} (fit on {r['fit on']}): cohort={r['cohort']:.5f} test={r['test']:.5f} "
                  f"({r['s']:.0f}s)", flush=True)
    print("\n| config | B cohort (fit A) | B test | C cohort (fit A+B) | C test |\n|---|---|---|---|---|")
    for cfg in FEATS:
        b, c = [next(r for r in rows if r["config"] == cfg and r["fold"] == n) for n in ["B", "C"]]
        print(f"| {cfg} | {b['cohort']:.5f} | {b['test']:.5f} | {c['cohort']:.5f} | {c['test']:.5f} |")
    print("reference: s9 on fold B (logs/s9_blend_pw.log): 0.35415 / 0.39739", flush=True)

    sf = Split("final", inter, unlab, eval_users=test_list)
    DF = S5.SplitData("final", inter, unlab, pairs, eval_users=test_list, users=[u for u in test_list if u in sf.hist])
    FF, LF, _ = DF.frame(S9.VARIANT, pairs)
    add_recency(DF, FF, pairs)
    Ftr = pd.concat([F["A"], F["B"], F["C"]], ignore_index=True)
    lists = H.score_lists(DF.sd, lists_for(FF, DF.sd, Ftr, FEATS["+ recency"], w, k), test_list)
    print(f"\n[final] fit on A+B+C stacked: rows={len(Ftr)} (A {len(F['A'])}, B {len(F['B'])}, C {len(F['C'])}), "
          f"label per target week (5 / 10 / 3); features: + recency; final frame rows={len(FF)} "
          f"users={FF.user_id.nunique()}")
    c = H.slot_sources(lists, test_list, H.h3_members(DF.C, LF))
    print("s10 slot sources (1260 test users): " + ", ".join(f"{s}={c[s]}" for s in H.SLOT_SOURCES))
    path = SUB_DIR / "s10_blend_abc.csv"
    write_submission(path, test_list, lists)
    validate_submission(path, DF.sd.pool_set)
    print(f"total {time.perf_counter() - t0:.0f}s")


if __name__ == "__main__":
    main()
