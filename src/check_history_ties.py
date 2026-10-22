"""History-by-count with the two tie-breaks (total train seconds vs global popularity) on folds A and B.
Run: .venv/bin/python src/check_history_ties.py"""
import methods as M
from load import load_sub
from protocol import Split, load_interactions, load_unlab, mapk

inter, unlab, test = load_interactions(), load_unlab(), set(load_sub().user_id)
for fold in ["A", "B"]:
    sd = Split(fold, inter, unlab)
    h = M.history_scores(sd, "count")
    ct = [u for u in sd.cohort if u in test]
    for name, keys in [("ties by seconds", ["score", "overlap_s", "grank"]), ("ties by popularity", ["score", "grank"])]:
        d = h.sort_values(["user_id"] + keys, ascending=[True, False] + [k != "overlap_s" and k != "score" for k in keys[1:]])
        l = sd.finish({u: g.tolist() for u, g in d.groupby("user_id").head(5).groupby("user_id").tv_show_id})
        print(f"[{fold}] history count, {name}: cohort={mapk(l, sd.truth, sd.cohort):.5f} test={mapk(l, sd.truth, ct):.5f}")
