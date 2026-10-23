"""s9: the s8 blend (rank fusion of poisson HGB + CatBoost YetiRank lr 0.03 depth 8, weights and k as chosen on
fold A in logs/s5_blend_grid.csv) with the B38 active-week fix (D62) and all 7 count features per week as in s7b
(D63); candidates = exposure source + top-60 everywhere; CatBoost averaged over seeds 42-46, HGB seed 42.
Fold B: both components fit on A. Final: both fit on A+B stacked (label per target week, D50), 11-30 -> 31-42.
Run: .venv/bin/python src/s9_blend_pw.py -> logs/s9_blend_pw.log, submissions/s9_blend_pw.csv
"""
import os

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")  # before numpy/sklearn load BLAS (BUGLOG B24)

import numpy as np
import pandas as pd

import s4b_hybrids as H
import s5_blend as BL
import s5_push as S5
import s7b_perweek as S7B  # sets SplitData.ACTIVE_WEEKS and the "s7b per-week" feature set
from load import ART, ROOT, load_sub
from protocol import Split, load_interactions, load_unlab
from s1_popularity import SUB_DIR, validate_submission, write_submission

VARIANT = "+ exposure source, top-60 everywhere"
FEATS = S5.FEATSETS["s7b per-week"]
HGB, CB = ("hgb",), ("cb", 0.03, 8)


def blend_params():
    g = pd.read_csv(ROOT / "logs" / "s5_blend_grid.csv")  # sorted by A cohort desc; first row = s8's choice
    b = g.iloc[0]
    return (b.w_hgb, b.w_cb, b.w_h2), int(b.k)


def blended(F, sd, Ftr, ytr, w, k):
    """Blend lists for the rows of F: HGB (seed 42) + CatBoost (mean of 5 seeds), fit on (Ftr, ytr)."""
    p_cb = np.zeros(len(F))
    for s in S5.BAG_SEEDS:
        p_cb += S5.fit_predict(CB, Ftr, ytr, F, FEATS, s) / len(S5.BAG_SEEDS)
    R = BL.merge_ranks([BL.ranks_from_pred(F, S5.fit_predict(HGB, Ftr, ytr, F, FEATS, 42), "hgb"),
                        BL.ranks_from_pred(F, p_cb, "cb")], sd)
    return BL.top_lists(R, BL.blend_score(R, w, k))


def main():
    inter, unlab = load_interactions(), load_unlab()
    test_list = load_sub().user_id.tolist()
    test = set(test_list)
    pairs = pd.read_parquet(ART / "view_airing_pairs.parquet",
                            columns=["user_id", "channel_id", "period", "week", "ov_start", "ov_end"])
    w, k = blend_params()
    assert w[2] == 0, "s8's fold-A blend gave H2 weight 0; this script fuses HGB + CatBoost only"
    print(f"blend w(hgb, cb, h2)={w} k={k} (logs/s5_blend_grid.csv); candidates: {VARIANT}; features: {FEATS}")
    DA, DB = S5.SplitData("A", inter, unlab, pairs), S5.SplitData("B", inter, unlab, pairs)
    FA, _, _ = DA.frame(VARIANT, pairs)
    FB, LB, _ = DB.frame(VARIANT, pairs)
    lB = H.score_lists(DB.sd, blended(FB, DB.sd, FA, FA.label_pw.values, w, k), DB.sd.cohort)
    m = H.fold_metrics(DB.sd, lB, H.h3_cand(DB.C, LB), test)
    print(f"s9 config on fold B (fit on A): cohort={m['cohort']:.5f} test={m['test']:.5f} "
          f"cand_recall={m['cand_recall']:.4f} (s8: 0.35316 / 0.39339)", flush=True)

    sf = Split("final", inter, unlab, eval_users=test_list)
    DF = S5.SplitData("final", inter, unlab, pairs, eval_users=test_list, users=[u for u in test_list if u in sf.hist])
    FF, LF, _ = DF.frame(VARIANT, pairs)
    Ftr = pd.concat([FA, FB], ignore_index=True)
    lists = H.score_lists(DF.sd, blended(FF, DF.sd, Ftr, Ftr.label_pw.values, w, k), test_list)
    print(f"[final] fit on A+B stacked: rows={len(Ftr)} (A {len(FA)}, B {len(FB)}), label per target week; "
          f"final frame rows={len(FF)} users={FF.user_id.nunique()}")
    c = H.slot_sources(lists, test_list, H.h3_members(DF.C, LF))
    print("s9 slot sources (1260 test users): " + ", ".join(f"{s}={c[s]}" for s in H.SLOT_SOURCES))
    path = SUB_DIR / "s9_blend_pw.csv"
    write_submission(path, test_list, lists)
    validate_submission(path, DF.sd.pool_set)


if __name__ == "__main__":
    main()
