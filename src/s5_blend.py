"""Step 5 item 7: weighted rank fusion of (a) H3+ poisson HGB, (b) CatBoostRanker YetiRank (config selected in
s5_push), (c) H2 RRF (fold-A weights). (a) and (b) use the candidate variant and feature set kept on fold A by
s5_push (parsed from logs/s5_push.log). Weights/k tuned on fold-A out-of-fold rankings, reported on fold B.
Run after src/s5_push.py: .venv/bin/python src/s5_blend.py -> logs/s5_blend.log, logs/s5_blend_grid.csv
"""
import os

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")  # before numpy/sklearn load BLAS (BUGLOG B24)

import itertools
import json
import re
import time
from types import SimpleNamespace

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

import s4b_hybrids as H
import s5_push as S5
from load import ART, ROOT, load_sub
from protocol import K, load_interactions, load_unlab, mapk
from s1_popularity import SUB_DIR, validate_submission, write_submission

CURRENT = list(S5.VARIANTS)[0]  # current candidates (5 sources, top-30): only for the H3+ reproduction line
MODELS = ["hgb", "cb", "h2"]
GRID = [w for w in itertools.product([0, 0.5, 1, 2], repeat=3) if any(w)]
KS = [5, 20]


def selected_cb():
    rows = pd.read_csv(ROOT / "logs" / "s5_rows.csv")
    r = rows[rows.name.str.contains(r"\(selected\)", regex=True)].iloc[0]
    return tuple(json.loads(r.model))


def kept_choices():
    """Candidate variant and feature set kept on fold A by s5_push (its '-> ... kept' log lines)."""
    log = (ROOT / "logs" / "s5_push.log").read_text()
    v = re.search(r"-> candidate variant kept \(.*?\): (.+)", log).group(1).strip()
    f = re.search(r"-> feature set kept \(argmax A\): (.+)", log).group(1).strip()
    assert v in S5.VARIANTS and f in S5.FEATSETS, (v, f)
    return v, f


def h2_params():
    g = pd.read_csv(ROOT / "logs" / "s4b_h2_grid.csv")
    b = g.loc[g.A_cohort.idxmax()]
    return {"history": b.w_hist, "PPR": b.w_ppr, "CBF": b.w_cbf, "ALS": b.w_als}, float(b.k)


def ranks_from_pred(F, pred, m):
    d = F[["user_id", "tv_show_id", "grank"]].assign(p=pred).sort_values(["user_id", "p", "grank"],
                                                                          ascending=[True, False, True])
    d["r_" + m] = d.groupby("user_id").cumcount() + 1
    return d[["user_id", "tv_show_id", "r_" + m]]


def h2_ranks(D):
    w, k = h2_params()
    shim = SimpleNamespace(lists=D.lists(30, False), sd=D.sd)
    wide = H.h2_wide(shim)
    s = sum(np.nan_to_num(wt / (k + wide[c].values)) for c, wt in w.items() if wt)
    d = wide.assign(score=s)
    d = d[d.score > 0].sort_values(["user_id", "score", "grank"], ascending=[True, False, True])
    d["r_h2"] = d.groupby("user_id").cumcount() + 1
    return d[["user_id", "tv_show_id", "r_h2"]]


def merge_ranks(parts, sd):
    R = parts[0]
    for p in parts[1:]:
        R = R.merge(p, on=["user_id", "tv_show_id"], how="outer")
    R["grank"] = R.tv_show_id.map(sd.poprank).values
    return R


def top_lists(R, score):
    d = R.assign(s=score)
    d = d[d.s > 0].sort_values(["user_id", "s", "grank"], ascending=[True, False, True])
    return {u: g.tolist() for u, g in d.groupby("user_id").head(K).groupby("user_id").tv_show_id}


def blend_score(R, w, k):
    return sum(np.nan_to_num(wt / (k + R["r_" + m].values)) for m, wt in zip(MODELS, w) if wt)


def single_lists(R, m):
    return top_lists(R, np.nan_to_num(1.0 / R["r_" + m].values))


def oof_pred(F, y, model, feats):
    oof = np.zeros(len(F))
    for i_tr, i_te in GroupKFold(n_splits=5).split(F, groups=F.user_id):
        oof[i_te] = S5.fit_predict(model, F.iloc[i_tr], y[i_tr], F.iloc[i_te], feats, 42)
    return oof


def main():
    inter, unlab = load_interactions(), load_unlab()
    test_list = load_sub().user_id.tolist()
    test = set(test_list)
    pairs = pd.read_parquet(ART / "view_airing_pairs.parquet",
                            columns=["user_id", "channel_id", "period", "week", "ov_start", "ov_end"])
    CB, HGB = selected_cb(), ("hgb",)
    variant, fs = kept_choices()
    feats = S5.FEATSETS[fs]
    print(f"CatBoost config from logs/s5_rows.csv: {CB}; H2 params from logs/s4b_h2_grid.csv: {h2_params()}; "
          f"(a)/(b) on kept candidates '{variant}' and features '{fs}' (from logs/s5_push.log)", flush=True)
    DA, DB = S5.SplitData("A", inter, unlab, pairs), S5.SplitData("B", inter, unlab, pairs)

    def ev(D, lists):
        l = H.score_lists(D.sd, lists, D.sd.cohort)
        ct = [u for u in D.sd.cohort if u in test]
        return mapk(l, D.sd.truth, D.sd.cohort), mapk(l, D.sd.truth, ct)

    # sanity: current H3+ (current candidates, raw features, poisson HGB) must reproduce step 4C
    FA0, _, _ = DA.frame(CURRENT, pairs)
    FB0, _, _ = DB.frame(CURRENT, pairs)
    a = ev(DA, H.h3_lists(FA0, oof_pred(FA0, FA0.label.values, HGB, S5.RAW)))
    b = ev(DB, H.h3_lists(FB0, S5.fit_predict(HGB, FA0, FA0.label.values, FB0, S5.RAW, 42)))
    print(f"SANITY current H3+: A cohort={a[0]:.5f} test={a[1]:.5f} | B cohort={b[0]:.5f} test={b[1]:.5f} "
          f"(step 4C: 0.37585 / 0.41734 | 0.35379 / 0.39499)", flush=True)

    FA, _, _ = DA.frame(variant, pairs)
    FB, _, _ = DB.frame(variant, pairs)
    yA = S5.label_of(FA, feats)
    t = time.perf_counter()
    RA = merge_ranks([ranks_from_pred(FA, oof_pred(FA, yA, HGB, feats), "hgb"),
                      ranks_from_pred(FA, oof_pred(FA, yA, CB, feats), "cb"), h2_ranks(DA)], DA.sd)
    RB = merge_ranks([ranks_from_pred(FB, S5.fit_predict(HGB, FA, yA, FB, feats, 42), "hgb"),
                      ranks_from_pred(FB, S5.fit_predict(CB, FA, yA, FB, feats, 42), "cb"),
                      h2_ranks(DB)], DB.sd)
    print(f"rankings built in {time.perf_counter() - t:.1f}s; A rows={len(RA)} B rows={len(RB)}", flush=True)

    single = {}
    for m in MODELS:
        a, b = ev(DA, single_lists(RA, m)), ev(DB, single_lists(RB, m))
        single[m] = (a, b)
        print(f"single {m}: A cohort={a[0]:.5f} test={a[1]:.5f} | B cohort={b[0]:.5f} test={b[1]:.5f}", flush=True)

    print("\n== pairwise top-5 overlap on fold B (warm cohort users, model output before fallback fill)")
    warm = [u for u in DB.sd.cohort if u in DB.sd.hist]
    tl = {m: single_lists(RB, m) for m in MODELS}
    for a, b in itertools.combinations(MODELS, 2):
        ov = np.array([len(set(tl[a].get(u, [])) & set(tl[b].get(u, []))) for u in warm])
        same_order = np.mean([tl[a].get(u) == tl[b].get(u) for u in warm])
        print(f"| {a} vs {b} | mean shared ids of 5: {ov.mean():.3f} | distribution 0..5: "
              f"{np.bincount(ov, minlength=6).tolist()} | identical ordered lists: {same_order:.3f} |")

    grid = []
    for w in GRID:
        for k in KS:
            a = ev(DA, top_lists(RA, blend_score(RA, w, k)))
            grid.append({"w_hgb": w[0], "w_cb": w[1], "w_h2": w[2], "k": k, "A_cohort": a[0], "A_test": a[1]})
    g = pd.DataFrame(grid).sort_values("A_cohort", ascending=False)
    g.to_csv(ROOT / "logs" / "s5_blend_grid.csv", index=False)
    best = g.iloc[0]
    w, k = (best.w_hgb, best.w_cb, best.w_h2), int(best.k)
    t = time.perf_counter()
    b = ev(DB, top_lists(RB, blend_score(RB, w, k)))
    tb = time.perf_counter() - t
    best_single = max(MODELS, key=lambda m: single[m][0][0])
    print(f"\nblend grid: {len(g)} points; top 5 on A:\n{g.head(5).to_string(index=False)}")
    print(f"\n| blend w(hgb, cb, h2)={w} k={k} | A cohort={best.A_cohort:.5f} test={best.A_test:.5f} | "
          f"B cohort={b[0]:.5f} test={b[1]:.5f} | blend step on B {tb:.2f}s |")
    print(f"best single model on A: {best_single} (A cohort {single[best_single][0][0]:.5f})")
    if best.A_cohort > single[best_single][0][0]:
        final_blend(inter, unlab, pairs, test_list, DA, DB, CB, w, k, variant, feats)
    else:
        print("blend does not beat the best single model on fold A -> no s8 file")


def final_blend(inter, unlab, pairs, test_list, DA, DB, CB, w, k, variant, feats):
    """Components fit as in DESIGN D50: (a), (b) on A+B stacked with per-week label; (c) H2 on 11-30 lists."""
    sf = S5.Split("final", inter, unlab, eval_users=test_list)
    DF = S5.SplitData("final", inter, unlab, pairs, eval_users=test_list, users=[u for u in test_list if u in sf.hist])
    FA, _, _ = DA.frame(variant, pairs)
    FB, _, _ = DB.frame(variant, pairs)
    FF, LF, _ = DF.frame(variant, pairs)
    Ftr = pd.concat([FA, FB], ignore_index=True)
    RF = merge_ranks([ranks_from_pred(FF, S5.fit_predict(("hgb",), Ftr, Ftr.label_pw.values, FF, feats, 42), "hgb"),
                      ranks_from_pred(FF, S5.fit_predict(CB, Ftr, Ftr.label_pw.values, FF, feats, 42), "cb"),
                      h2_ranks(DF)], DF.sd)
    lists = H.score_lists(DF.sd, top_lists(RF, blend_score(RF, w, k)), test_list)
    c = H.slot_sources(lists, test_list, H.h3_members(DF.C, LF))
    print(f"[final] stacked rows={len(Ftr)}; final rankings rows={len(RF)} users={RF.user_id.nunique()}")
    print("s8 slot sources (1260 test users): " + ", ".join(f"{s}={c[s]}" for s in H.SLOT_SOURCES))
    path = SUB_DIR / "s8_blend.csv"
    write_submission(path, test_list, lists)
    validate_submission(path, DF.sd.pool_set)


if __name__ == "__main__":
    main()
