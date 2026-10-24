"""Step 6: two example users on fold B (train 11-20 -> target 21-30), same users for every method.
Rule (DESIGN D68): among the 1,260 test users in the fold-B cohort, heavy = top 10% of the 1,260 test users by
train positive airings (fold-B train window; cold users count 0), light = 1-3 distinct train positive programmes;
one seed-42 random pick from each group. Methods: popularity, history (count), PPR x air, CBF x air, ALS x air
(fold-A params from logs/s4a_selected.json) and the s8 blend rebuilt on fold B exactly as in src/s5_blend.py
(fit on A; kept candidates + per-week features, with the active-week counting s8 had).
Each method's list is its finished top-5 (method output + shared fallback), the list that is scored.
Run: .venv/bin/python src/examples.py -> logs/examples.log, logs/examples.md
"""
import os

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")  # before numpy/sklearn load BLAS (BUGLOG B24)

import json

import numpy as np
import pandas as pd

import methods as M
import s4b_hybrids as H
import s5_blend as BL
import s5_push as S5
from load import ART, ROOT, load_sub
from protocol import apk, load_interactions, load_unlab, mapk, sched_window

SEL = json.loads((ROOT / "logs" / "s4a_selected.json").read_text())
assert S5.SplitData.ACTIVE_WEEKS is None  # s8 was built without the D62 fix


def s8_lists(inter, unlab, pairs):
    w, k = (0.5, 0.5, 0.0), 5
    g = pd.read_csv(ROOT / "logs" / "s5_blend_grid.csv").iloc[0]
    assert (g.w_hgb, g.w_cb, g.w_h2, int(g.k)) == (*w, k)
    variant, fs = BL.kept_choices()
    feats = S5.FEATSETS[fs]
    DA, DB = S5.SplitData("A", inter, unlab, pairs), S5.SplitData("B", inter, unlab, pairs)
    FA, _, _ = DA.frame(variant, pairs)
    FB, _, _ = DB.frame(variant, pairs)
    yA = S5.label_of(FA, feats)
    R = BL.merge_ranks([BL.ranks_from_pred(FB, S5.fit_predict(("hgb",), FA, yA, FB, feats, 42), "hgb"),
                        BL.ranks_from_pred(FB, S5.fit_predict(BL.selected_cb(), FA, yA, FB, feats, 42), "cb")], DB.sd)
    return DB.sd, BL.top_lists(R, BL.blend_score(R, w, k))


def main():
    inter, unlab = load_interactions(), load_unlab()
    test_list = load_sub().user_id.tolist()
    test = set(test_list)
    pairs = pd.read_parquet(ART / "view_airing_pairs.parquet",
                            columns=["user_id", "channel_id", "period", "week", "ov_start", "ov_end"])
    sd, raw = s8_lists(inter, unlab, pairs)
    ct = [u for u in sd.cohort if u in test]
    warm = [u for u in sd.cohort if u in sd.hist]

    raws = {"popularity": {u: sd.pop.tv_show_id.head(5).tolist() for u in warm},
            "history (count)": M.history_lists(sd, "count")}
    a = SEL["PPR x air"]["alpha"]
    items, S, _ = M.ppr_scores(sd, warm, a)
    raws[f"PPR x air (alpha {a})"] = M.rank_lists(sd, warm, items, S * M.air_weight(sd, items), True)
    items, S, _ = M.cbf_scores(sd, warm)
    raws["CBF x air"] = M.rank_lists(sd, warm, items, S * M.air_weight(sd, items), True)
    p = SEL["ALS x air"]
    items, S = M.als_scores(sd, warm, p["conf"], p["factors"], p["reg"], p["alpha"])
    raws[f"ALS x air ({p['conf']}, f={p['factors']}, reg={p['reg']}, alpha={p['alpha']})"] = \
        M.rank_lists(sd, warm, items, S * M.air_weight(sd, items), False)
    raws["s8 blend (HGB + CatBoost rank fusion)"] = raw
    lists = {}
    for name, r in raws.items():
        lists[name] = sd.finish(r)
        print(f"{name}: fold B cohort={mapk(lists[name], sd.truth, sd.cohort):.5f} "
              f"test={mapk(lists[name], sd.truth, ct):.5f}", flush=True)

    # ---- user pick
    npos = sd.pos.groupby("user_id").size().reindex(test_list).fillna(0)
    thr = npos.quantile(0.9)
    nprog = sd.up.groupby("user_id").size()
    heavy = sorted(u for u in ct if npos[u] >= thr)
    light = sorted(u for u in ct if 1 <= nprog.get(u, 0) <= 3)
    # second light rule (D69): the first light pick had 1 truth item = its 1 history item, so every personalised
    # method scored 1.0; requiring >= 3 truth programmes makes the example informative. Separate seed-42 draw.
    light2 = sorted(u for u in light if len(sd.truth[u]) >= 3)
    rng = np.random.default_rng(42)
    users = {"heavy": heavy[rng.integers(len(heavy))], "light": light[rng.integers(len(light))]}
    users["light (rule 2: >= 3 truth programmes)"] = light2[np.random.default_rng(42).integers(len(light2))]
    print(f"heavy threshold (90th pct of train positive airings over 1,260 test users) = {thr:.0f}; "
          f"eligible heavy={len(heavy)} light={len(light)} light rule 2={len(light2)}; picked {users}")

    meta = pd.concat([sched_window(sd.train_windows), sd.pool_sched])
    title = meta.groupby("tv_show_id").tv_show_title.agg(lambda x: x.value_counts().index[0])
    cat = meta.groupby("tv_show_id").tv_show_category.agg(lambda x: x.value_counts().index[0])
    clean = lambda s: str(s).replace("|", "/")
    out = []
    for kind, u in users.items():
        hist, truth = sd.hist.get(u, set()), sd.truth[u]
        up = sd.up[sd.up.user_id == u].sort_values(["n_pos", "overlap_s", "tv_show_id"], ascending=[False, False, True])
        out.append(f"\n#### {kind} viewer `{u}`: {int(npos[u])} train positive airings over {len(up)} programmes "
                   f"(weeks 11-20); {len(truth)} truth programmes in 21-30\n")
        out.append("Train history top-10 (11-20):\n\n| # | id | title | category | positives |\n|---|---|---|---|---|")
        for i, r in enumerate(up.head(10).itertuples(), 1):
            out.append(f"| {i} | {r.tv_show_id} | {clean(title.get(r.tv_show_id))} | {clean(cat.get(r.tv_show_id))} | {r.n_pos} |")
        out.append(f"\nTruth 21-30 (in order): {', '.join(f'{p} {clean(title.get(p))}' for p in truth)}\n")
        out.append("| method | AP@5 | 1 | 2 | 3 | 4 | 5 |\n|---|---|---|---|---|---|---|")
        for name, l in lists.items():
            r = raws[name].get(u, [])
            cells = []
            for i, p in enumerate(l[u]):
                tags = ("R" if p in hist else "") + ("T" if p in truth else "") + ("" if i < len(r) and r[i] == p else "f")
                cells.append(f"{p} {clean(title.get(p))} ({clean(cat.get(p))}){' **' + tags + '**' if tags else ''}")
            out.append(f"| {name} | {apk(l[u], truth):.3f} | "
                       + " | ".join(cells) + " |")
    out.insert(0, "Tags: **R** = re-watch (the user had ≥ 1 positive airing of this programme in train 11-20); "
                  "**T** = in the user's 21-30 truth; **f** = slot filled by the shared fallback, not by the method.")
    md = "\n".join(out)
    (ROOT / "logs" / "examples.md").write_text(md + "\n")
    print(md)


if __name__ == "__main__":
    main()
