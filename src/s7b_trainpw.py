"""PREPARED, NOT RUN (DESIGN D60): final variant of s7 in which the train-window count features are rescaled to
the length of the train window of their own split: n_pos, overlap_s -> per active train week of the user (nominal ISO train weeks only, D62);
pop, air_tr -> per train week of the split (A 5, B 10, final 20). Everything else as s7: CatBoost YetiRank
lr 0.03 depth 8, seeds 42-46, current candidates, fit on A+B stacked with label per target week (D50),
applied to 11-30 -> 31-42. Target-window features (air_t, exp_all, exp_top3) stay raw, as in s7.
Run:   .venv/bin/python src/s7b_trainpw.py          -> submissions/s7b_trainpw.csv (logs/s7b_trainpw.log)
Check: .venv/bin/python src/s7b_trainpw.py --check  -> builds the A/B frames only, asserts the columns, no fit
"""
import os

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")  # before numpy/sklearn load BLAS (BUGLOG B24)

import json
import sys

import numpy as np
import pandas as pd

import s5_push as S5
from load import ART, load_sub
from protocol import load_interactions, load_unlab

TRAIN_PW = {"n_pos": "n_pos_pw", "overlap_s": "overlap_pw", "pop": "pop_pw", "air_tr": "air_tr_pw"}
S5.SplitData.ACTIVE_WEEKS = {"A": (11, 15), "B": (11, 20), "final": (11, 30)}  # DESIGN D62, BUGLOG B38
S5.FEATSETS["train-per-week"] = [TRAIN_PW.get(f, f) for f in S5.RAW]
BEST = {"variant": list(S5.VARIANTS)[0], "features": "train-per-week", "model": json.dumps(["cb", 0.03, 8]),
        "seeds": 5}


def main(check=False):
    inter, unlab = load_interactions(), load_unlab()
    test_list = load_sub().user_id.tolist()
    pairs = pd.read_parquet(ART / "view_airing_pairs.parquet",
                            columns=["user_id", "channel_id", "period", "week", "ov_start", "ov_end"])
    DA, DB = S5.SplitData("A", inter, unlab, pairs), S5.SplitData("B", inter, unlab, pairs)
    feats = S5.FEATSETS["train-per-week"]
    print(f"features ({len(feats)}): {feats}")
    if check:
        for D in (DA, DB):
            F, _, _ = D.frame(BEST["variant"], pairs)
            X = F[[f for f in feats if f != "category"]]
            assert np.isfinite(F[list(TRAIN_PW.values())].values).all(), "non-finite per-week feature"
            print(f"[{D.sd.name}] rows={len(F)}; train-window per-week columns: "
                  + ", ".join(f"{c} mean={F[c].mean():.4g}" for c in TRAIN_PW.values())
                  + f"; NaN share over all features={X.isna().values.mean():.4f}")
        return
    S5.final_s7(inter, unlab, pairs, test_list, DA, DB, BEST, out="s7b_trainpw.csv")


if __name__ == "__main__":
    main(check="--check" in sys.argv)
