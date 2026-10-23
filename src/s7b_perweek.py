"""PREPARED, NOT RUN (DESIGN D60, D63): final variant of s7 in which every count feature is rescaled to the length
of the window it is counted in, in its own split:
  train window:  n_pos, overlap_s -> per active train week of the user (nominal ISO train weeks only, D62);
                 pop, air_tr      -> per train week of the split (A 5, B 10, final 20)
  target window: air_t, exp_all, exp_top3 -> per target week (A 5, B 10, final 12), the same divisor as the label
Everything else as s7: CatBoost YetiRank lr 0.03 depth 8, seeds 42-46, current candidates, fit on A+B stacked with
label = positives per target week (D50), applied to 11-30 -> 31-42.
Run:   .venv/bin/python src/s7b_perweek.py          -> fold-B score (fit on A), then submissions/s7b_perweek.csv
                                                       (logs/s7b_perweek.log)
Check: .venv/bin/python src/s7b_perweek.py --check  -> builds the A/B frames only, asserts the columns, no fit
"""
import os

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")  # before numpy/sklearn load BLAS (BUGLOG B24)

import json
import sys

import numpy as np
import pandas as pd

import s4b_hybrids as H
import s5_push as S5
from load import ART, load_sub
from protocol import load_interactions, load_unlab

PW = {"n_pos": "n_pos_pw", "overlap_s": "overlap_pw", "pop": "pop_pw", "air_tr": "air_tr_pw",  # train window
      "air_t": "air_t_pw", "exp_all": "exp_all_pw", "exp_top3": "exp_top3_pw"}              # target window
S5.SplitData.ACTIVE_WEEKS = {"A": (11, 15), "B": (11, 20), "final": (11, 30)}  # DESIGN D62, BUGLOG B38
S5.FEATSETS["s7b per-week"] = [PW.get(f, f) for f in S5.RAW]
BEST = {"variant": list(S5.VARIANTS)[0], "features": "s7b per-week", "model": json.dumps(["cb", 0.03, 8]),
        "seeds": 5}


def main(check=False):
    inter, unlab = load_interactions(), load_unlab()
    test_list = load_sub().user_id.tolist()
    pairs = pd.read_parquet(ART / "view_airing_pairs.parquet",
                            columns=["user_id", "channel_id", "period", "week", "ov_start", "ov_end"])
    DA, DB = S5.SplitData("A", inter, unlab, pairs), S5.SplitData("B", inter, unlab, pairs)
    feats = S5.FEATSETS["s7b per-week"]
    assert not set(PW) & set(feats) and set(PW.values()) <= set(feats), "a raw count left in the feature set"
    print(f"features ({len(feats)}): {feats}")
    if check:
        for D in (DA, DB):
            F, _, _ = D.frame(BEST["variant"], pairs)
            X = F[[f for f in feats if f != "category"]]
            assert np.isfinite(F[list(PW.values())].values).all(), "non-finite per-week feature"
            print(f"[{D.sd.name}] rows={len(F)}; per-week columns: "
                  + ", ".join(f"{c} mean={F[c].mean():.4g}" for c in PW.values())
                  + f"; NaN share over all features={X.isna().values.mean():.4f}")
        return
    eval_b(DA, DB, set(test_list), pairs)
    S5.final_s7(inter, unlab, pairs, test_list, DA, DB, BEST, out="s7b_perweek.csv")


def eval_b(DA, DB, test, pairs):
    """Fold-B score of the s7b config, fit on A (label per target week, as S5.label_of gives for per-week sets)."""
    feats = S5.FEATSETS["s7b per-week"]
    FA, _, _ = DA.frame(BEST["variant"], pairs)
    FB, LB, _ = DB.frame(BEST["variant"], pairs)
    p = np.zeros(len(FB))
    for s in S5.BAG_SEEDS:
        p += S5.fit_predict(("cb", 0.03, 8), FA, S5.label_of(FA, feats), FB, feats, s) / len(S5.BAG_SEEDS)
    m = H.fold_metrics(DB.sd, H.score_lists(DB.sd, H.h3_lists(FB, p), DB.sd.cohort), H.h3_cand(DB.C, LB), test)
    print(f"s7b config on fold B (fit on A): cohort={m['cohort']:.5f} test={m['test']:.5f} "
          f"cand_recall={m['cand_recall']:.4f} (s7: 0.35415 / 0.39646)", flush=True)


if __name__ == "__main__":
    main(check="--check" in sys.argv)
