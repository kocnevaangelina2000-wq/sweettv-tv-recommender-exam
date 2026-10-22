"""Step 5: is CatBoostRanker (YetiRank, lr 0.03, depth 8) deterministic for a fixed seed? Two fits, same data.
Synthetic grouped data (no fold rows needed: the question is about the library, not our features).
Run: .venv/bin/python src/check_cb_determinism.py -> logs/check_cb_determinism.log
"""
import numpy as np
import pandas as pd

import s5_push as S5

rng = np.random.default_rng(42)
n_users, per = 2000, 30
F = pd.DataFrame({"user_id": np.repeat(np.arange(n_users), per)})
feats = ["x1", "x2", "x3", "category"]
for c in ["x1", "x2", "x3"]:
    F[c] = rng.normal(size=len(F))
F["category"] = rng.integers(0, 10, len(F))
y = rng.poisson(np.exp(0.5 * F.x1 - 0.3 * F.x2)).astype(float)
p = [S5.fit_predict(("cb", 0.03, 8), F, y, F, feats, 42) for _ in range(2)]
q = S5.fit_predict(("cb", 0.03, 8), F, y, F, feats, 43)
print(f"rows={len(F)} groups={n_users}; seed 42 vs seed 42: max |diff|={np.abs(p[0] - p[1]).max():.3e}, "
      f"identical={np.array_equal(p[0], p[1])}; seed 42 vs 43: max |diff|={np.abs(p[0] - q).max():.3e}")
