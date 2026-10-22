"""Why does H3's HistGradientBoostingRegressor stop after 10 iterations? Inspect validation scores on fold A.
Run: .venv/bin/python src/check_hgb_stopping.py -> logs/check_hgb_stopping.log"""
import os

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import numpy as np

import s4b_hybrids as H
from protocol import Split, load_interactions, load_unlab

inter, unlab = load_interactions(), load_unlab()
sd = Split("A", inter, unlab)
F = H.h3_frame(H.Components(sd, sd.warm, []))
m = H.hgb().fit(F[H.FEATURES], F.label)
print(f"early_stopping={m.early_stopping} do_early_stopping_={m.do_early_stopping_} n_iter_={m.n_iter_} "
      f"scoring={m.scoring} validation_fraction={m.validation_fraction}")
print("train_score_ (neg poisson deviance-like loss):", np.round(m.train_score_, 6).tolist())
print("validation_score_:", np.round(m.validation_score_, 6).tolist())
print(f"label mean={F.label.mean():.4f} var={F.label.var():.4f} max={F.label.max()}; "
      f"pred std={m.predict(F[H.FEATURES]).std():.4f}")

# learning-rate sweep on fold A only (poisson loss, seed 42, early stopping on): does training stay stable?
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold
from protocol import mapk

for lr in [0.1, 0.05, 0.02, 0.01]:
    mk = lambda: HistGradientBoostingRegressor(loss="poisson", random_state=42, learning_rate=lr, max_iter=1000,
                                               categorical_features=[H.FEATURES.index("category")])
    m = mk().fit(F[H.FEATURES], F.label)
    v = m.validation_score_
    oof = np.zeros(len(F))
    for i_tr, i_te in GroupKFold(n_splits=5).split(F, groups=F.user_id):
        oof[i_te] = mk().fit(F.iloc[i_tr][H.FEATURES], F.iloc[i_tr].label).predict(F.iloc[i_te][H.FEATURES])
    lists = H.score_lists(sd, H.h3_lists(F, oof), sd.cohort)
    print(f"lr={lr}: n_iter_={m.n_iter_} val loss it0={-v[0]:.4f} it1={-v[1]:.4f} best={-v.max():.4f} at it {int(v.argmax())} "
          f"last={-v[-1]:.4f}; max val loss={-v.min():.4g}; pred max={m.predict(F[H.FEATURES]).max():.2f} "
          f"| A OOF MAP@5 cohort={mapk(lists, sd.truth, sd.cohort):.5f}", flush=True)
