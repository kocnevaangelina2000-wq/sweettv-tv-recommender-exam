"""Step 4 part B: hybrids H1 (history-first), H2 (weighted RRF), H3 (HistGradientBoosting re-ranker).
Tuned on fold A, reported on fold B; final = train 11-30 -> 31-42. Uses params from logs/s4a_selected.json.
Run: .venv/bin/python src/s4b_hybrids.py -> logs/s4b_hybrids.log, logs/s4b_h2_grid.csv
"""
import os

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")  # before numpy/sklearn load BLAS (BUGLOG B24)

import itertools
import json
import time

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold

import methods as M
from load import ROOT, SCHED_FILES, load_sched, load_sub
from protocol import K, Split, channel_share, check_lists, fill, load_interactions, load_unlab, mapk
from s1_popularity import SUB_DIR, validate_submission, write_submission

SEED = 42
TOPN = 30
SEL = json.loads((ROOT / "logs" / "s4a_selected.json").read_text())
PPR_ALPHAS = [0.3, 0.5, 0.7, 0.85]
H2_GRID = list(itertools.product([1, 2, 4], [0, 0.5, 1], [0, 0.5, 1], [0, 0.5, 1], [10, 60]))
SLOT_SOURCES = ["history", "PPR", "CBF", "ALS", "popularity", "fallback"]
CATS = sorted(set().union(*[set(load_sched(p).tv_show_category) for p in SCHED_FILES]))
FEATURES = ["n_pos", "overlap_s", "last_week_ago", "share_pos", "ppr", "ppr_rank", "als", "als_rank", "cbf",
            "cbf_rank", "pop", "air_t", "air_tr", "chan_share", "category"]


def to_long(lists, source):
    rows = [(u, p, r) for u, l in lists.items() for r, p in enumerate(l, 1)]
    return pd.DataFrame(rows, columns=["user_id", "tv_show_id", "rank"]).assign(source=source)


class Components:
    """Method outputs on one split for `users` (all warm users of the split, or the warm test users)."""

    def __init__(self, sd, users, ppr_alphas):
        self.sd, self.users = sd, list(users)
        self.times = {}
        t = time.perf_counter()
        h = M.history_scores(sd, "count")
        self.hist = h[h.user_id.isin(set(self.users))]
        hl = M.history_lists(sd, "count", topn=TOPN)
        self.hist_lists = {u: hl[u] for u in self.users if u in hl}  # only component users (BUGLOG B25)
        self.hist_all = {u: set(g) for u, g in self.hist.groupby("user_id").tv_show_id}
        self.times["history"] = time.perf_counter() - t
        self.ppr = {}
        for a in sorted(set(ppr_alphas) | {SEL["PPR x air"]["alpha"]}):
            t = time.perf_counter()
            items, S, conv = M.ppr_scores(sd, self.users, a)
            self.ppr[a] = (items, S)
            self.times[f"PPR a={a}"] = time.perf_counter() - t
            print(f"   [{sd.name}] PPR alpha={a}: {conv}", flush=True)
        p = SEL["ALS x air"]
        t = time.perf_counter()
        self.als = M.als_scores(sd, self.users, p["conf"], p["factors"], p["reg"], p["alpha"])
        self.times["ALS"] = time.perf_counter() - t
        t = time.perf_counter()
        self.cbf = M.cbf_scores(sd, self.users)[:2]
        self.times["CBF"] = time.perf_counter() - t
        a = SEL["PPR x air"]["alpha"]
        self.lists = {"history": self.hist_lists}
        for name, (items, S), pos_only in [("PPR", self.ppr[a], True), ("CBF", self.cbf, True), ("ALS", self.als, False)]:
            self.lists[name] = M.rank_lists(sd, self.users, items, S * M.air_weight(sd, items), pos_only, TOPN)
        glob = sd.pop.tv_show_id.head(TOPN).tolist()
        self.lists["popularity"] = {u: glob for u in self.users}

    def ppr_air_list(self, a):
        items, S = self.ppr[a]
        return M.rank_lists(self.sd, self.users, items, S * M.air_weight(self.sd, items), True, TOPN)


# ---------------------------------------------------------------- shared evaluation helpers
def score_lists(sd, partial, users):
    lists = sd.finish(partial, users)
    check_lists(lists, sd.pool_set)
    return lists


def fold_metrics(sd, lists, cand, test):
    ct = [u for u in sd.cohort if u in test]
    n_truth = sum(len(t) for t in sd.truth.values())
    hit = sum(len(set(t) & (cand.get(u, set()) | set(sd.fb[u]))) for u, t in sd.truth.items())
    ncand = np.mean([len(cand.get(u, set()) | set(sd.fb[u])) for u in sd.cohort])
    return {"cohort": mapk(lists, sd.truth, sd.cohort), "test": mapk(lists, sd.truth, ct),
            "cand_recall": hit / n_truth, "mean_cands": float(ncand)}


def slot_sources(lists, users, members):
    """Each slot -> first source (priority order) whose input contains the item; else fallback."""
    cnt = dict.fromkeys(SLOT_SOURCES, 0)
    for u in users:
        for p in lists[u]:
            for s in SLOT_SOURCES[:-1]:
                if s in members and p in members[s].get(u, ()):
                    cnt[s] += 1
                    break
            else:
                cnt["fallback"] += 1
    return cnt


# ---------------------------------------------------------------- H1
def h1(C, a):
    items, S = C.ppr[a]
    r = pd.Index(C.users).get_indexer(C.hist.user_id)
    c = pd.Index(items).get_indexer(C.hist.tv_show_id)
    assert (r >= 0).all() and (c >= 0).all()
    h = C.hist.assign(ppr=S[r, c]).sort_values(["user_id", "n_pos", "ppr", "grank"],
                                               ascending=[True, False, False, True])
    hl = {u: g.tolist() for u, g in h.groupby("user_id").tv_show_id}
    pl = C.ppr_air_list(a)
    partial = {u: fill(hl.get(u, []) + pl.get(u, []), [], K) for u in C.users}
    cand = {u: set(hl.get(u, [])) | set(pl.get(u, [])) for u in C.users}
    members = {"history": C.hist_all, "PPR": {u: set(l) for u, l in pl.items()}}
    return partial, cand, members


# ---------------------------------------------------------------- H2
def h2_wide(C):
    lg = pd.concat([to_long(C.lists[s], s) for s in ["history", "PPR", "CBF", "ALS"]])
    w = lg.pivot_table(index=["user_id", "tv_show_id"], columns="source", values="rank").reset_index()
    for s in ["history", "PPR", "CBF", "ALS"]:
        if s not in w:
            w[s] = np.nan
    w["grank"] = w.tv_show_id.map(C.sd.poprank).values
    return w


def h2(C, wide, wh, wp, wc, wa, k):
    s = np.zeros(len(wide))
    for col, wt in [("history", wh), ("PPR", wp), ("CBF", wc), ("ALS", wa)]:
        if wt:
            s += np.nan_to_num(wt / (k + wide[col].values))
    d = wide.assign(score=s)
    d = d[d.score > 0].sort_values(["user_id", "score", "grank"], ascending=[True, False, True])
    partial = {u: g.tolist() for u, g in d.groupby("user_id").head(K).groupby("user_id").tv_show_id}
    used = [n for n, wt in [("history", wh), ("PPR", wp), ("CBF", wc), ("ALS", wa)] if wt]
    cand = {u: set().union(*[set(C.lists[n].get(u, [])) for n in used]) for u in C.users}
    members = {"history": C.hist_all, **{n: {u: set(l) for u, l in C.lists[n].items()} for n in used if n != "history"}}
    return partial, cand, members


# ---------------------------------------------------------------- H3
def h3_frame(C):
    sd = C.sd
    cand = pd.concat([to_long(C.lists[s], s) for s in ["history", "PPR", "CBF", "ALS", "popularity"]])
    f = cand[["user_id", "tv_show_id"]].drop_duplicates().reset_index(drop=True)
    f = f.merge(sd.up_all[["user_id", "tv_show_id", "n_pos", "overlap_s", "last_week"]], how="left",
                on=["user_id", "tv_show_id"])
    f["n_pos"] = f.n_pos.fillna(0)
    f["overlap_s"] = f.overlap_s.fillna(0)
    f["last_week_ago"] = sd.train_end_week - f.last_week  # NaN = never watched in train
    tot = sd.up.groupby("user_id").n_pos.sum()
    f["share_pos"] = f.n_pos / f.user_id.map(tot).values
    a = SEL["PPR x air"]["alpha"]
    for name, (items, S) in [("ppr", C.ppr[a]), ("als", C.als), ("cbf", C.cbf)]:
        R = M.full_ranks(S)
        r = pd.Index(C.users).get_indexer(f.user_id)
        assert (r >= 0).all(), "candidate user without component scores"
        c = pd.Index(items).get_indexer(f.tv_show_id)
        ok = c >= 0
        f[name] = np.where(ok, S[r, np.where(ok, c, 0)], np.nan)
        f[name + "_rank"] = np.where(ok, R[r, np.where(ok, c, 0)], np.nan)
    f["pop"] = f.tv_show_id.map(sd.pop.set_index("tv_show_id").n_pos).values
    f["air_t"] = f.tv_show_id.map(sd.air_t).fillna(0).values
    f["air_tr"] = f.tv_show_id.map(sd.air_tr).fillna(0).values
    cs = channel_share(C.users, sd.tr, sd.unlab_tr)
    pc = sd.pool_sched[["tv_show_id", "channel_id"]].drop_duplicates()
    chs = cs.merge(pc, on="channel_id").groupby(["user_id", "tv_show_id"]).share.sum()
    f["chan_share"] = chs.reindex(pd.MultiIndex.from_frame(f[["user_id", "tv_show_id"]])).fillna(0).values
    cat = sd.pool_sched.groupby("tv_show_id").tv_show_category.first()
    f["category"] = f.tv_show_id.map(cat).map({c: i for i, c in enumerate(CATS)}).values
    if sd.target_up is not None:
        lab = sd.target_up.set_index(["user_id", "tv_show_id"]).n_pos
        f["label"] = lab.reindex(pd.MultiIndex.from_frame(f[["user_id", "tv_show_id"]])).fillna(0).values
    f["grank"] = f.tv_show_id.map(sd.poprank).values
    return f


def hgb_for(feats):
    return HistGradientBoostingRegressor(loss="poisson", random_state=SEED,
                                         categorical_features=[feats.index("category")])


def hgb():
    return hgb_for(FEATURES)


def h3_lists(f, pred):
    d = f.assign(pred=pred).sort_values(["user_id", "pred", "grank"], ascending=[True, False, True])
    return {u: g.tolist() for u, g in d.groupby("user_id").head(K).groupby("user_id").tv_show_id}


def h3_members(C):
    return {"history": C.hist_all, **{n: {u: set(l) for u, l in C.lists[n].items()}
                                      for n in ["PPR", "CBF", "ALS", "popularity"]}}


def h3_cand(C):
    return {u: set().union(*[set(C.lists[n].get(u, [])) for n in ["history", "PPR", "CBF", "ALS", "popularity"]])
            for u in C.users}


# ---------------------------------------------------------------- main
def main():
    inter, unlab = load_interactions(), load_unlab()
    test_list = load_sub().user_id.tolist()
    test = set(test_list)
    S = {f: Split(f, inter, unlab) for f in ["A", "B"]}
    C = {}
    for f in ["A", "B"]:
        print(S[f].describe(), flush=True)
        t = time.perf_counter()
        C[f] = Components(S[f], S[f].warm, PPR_ALPHAS if f == "A" else [])
        print(f"   [{f}] components built in {time.perf_counter() - t:.1f}s: "
              f"{ {k: round(v, 2) for k, v in C[f].times.items()} }", flush=True)
    res = []

    # H1: tune alpha on A
    h1_rows = []
    for a in PPR_ALPHAS:
        partial, cand, _ = h1(C["A"], a)
        m = fold_metrics(S["A"], score_lists(S["A"], partial, S["A"].cohort), cand, test)
        h1_rows.append((a, m))
        print(f"H1 [A] alpha={a}: {m}", flush=True)
    a1 = max(h1_rows, key=lambda x: x[1]["cohort"])[0]
    if a1 not in C["B"].ppr:
        t = time.perf_counter()
        C["B"].ppr[a1] = M.ppr_scores(S["B"], C["B"].users, a1)[:2]
        C["B"].times[f"PPR a={a1}"] = time.perf_counter() - t
    mA = dict(h1_rows)[a1]
    t = time.perf_counter()
    partial, cand, _ = h1(C["B"], a1)
    lB = score_lists(S["B"], partial, S["B"].cohort)
    tB = time.perf_counter() - t
    mB = fold_metrics(S["B"], lB, cand, test)
    res.append(("H1 history-first", {"ppr_alpha": a1}, mA, mB, tB, C["B"].times["history"] + C["B"].times[f"PPR a={a1}"]))

    # H2: tune weights on A
    wA, wB = h2_wide(C["A"]), h2_wide(C["B"])
    grid = []
    for wh, wp, wc, wa, k in H2_GRID:
        partial, cand, _ = h2(C["A"], wA, wh, wp, wc, wa, k)
        m = fold_metrics(S["A"], score_lists(S["A"], partial, S["A"].cohort), cand, test)
        grid.append({"w_hist": wh, "w_ppr": wp, "w_cbf": wc, "w_als": wa, "k": k, **{f"A_{x}": v for x, v in m.items()}})
    g2 = pd.DataFrame(grid)
    best = g2.loc[g2.A_cohort.idxmax()]
    w2 = (best.w_hist, best.w_ppr, best.w_cbf, best.w_als, int(best.k))
    print(f"H2 grid ({len(g2)} points) best on A: {w2} A cohort={best.A_cohort:.5f}", flush=True)
    t = time.perf_counter()
    partial, cand, _ = h2(C["B"], wB, *w2)
    lB = score_lists(S["B"], partial, S["B"].cohort)
    tB = time.perf_counter() - t
    mB = fold_metrics(S["B"], lB, cand, test)
    g2.to_csv(ROOT / "logs" / "s4b_h2_grid.csv", index=False)
    mA = {x: best[f"A_{x}"] for x in ["cohort", "test", "cand_recall", "mean_cands"]}
    comp_B = sum(v for k, v in C["B"].times.items() if k in ["history", "CBF", "ALS", f"PPR a={SEL['PPR x air']['alpha']}"])
    res.append(("H2 weighted RRF", dict(zip(["w_hist", "w_ppr", "w_cbf", "w_als", "k"], map(float, w2))), mA, mB, tB, comp_B))

    # H3: features + HGB poisson
    t = time.perf_counter()
    FA = h3_frame(C["A"])
    t = time.perf_counter()
    FB = h3_frame(C["B"])
    t_feat = time.perf_counter() - t  # fold-B feature frame only
    print(f"H3 frames: A rows={len(FA)} users={FA.user_id.nunique()} label>0={(FA.label > 0).mean():.4f}; "
          f"B rows={len(FB)} users={FB.user_id.nunique()} label>0={(FB.label > 0).mean():.4f}; B frame built in {t_feat:.1f}s", flush=True)
    oof = np.zeros(len(FA))
    for k_, (i_tr, i_te) in enumerate(GroupKFold(n_splits=5).split(FA, groups=FA.user_id)):
        m = hgb().fit(FA.iloc[i_tr][FEATURES], FA.iloc[i_tr].label)
        oof[i_te] = m.predict(FA.iloc[i_te][FEATURES])
    mA = fold_metrics(S["A"], score_lists(S["A"], h3_lists(FA, oof), S["A"].cohort), h3_cand(C["A"]), test)
    print(f"H3 [A] 5-fold grouped-by-user out-of-fold: {mA}", flush=True)
    t = time.perf_counter()
    model_A = hgb().fit(FA[FEATURES], FA.label)
    lB = score_lists(S["B"], h3_lists(FB, model_A.predict(FB[FEATURES])), S["B"].cohort)
    tB = time.perf_counter() - t
    mB = fold_metrics(S["B"], lB, h3_cand(C["B"]), test)
    ins = fold_metrics(S["A"], score_lists(S["A"], h3_lists(FA, model_A.predict(FA[FEATURES])), S["A"].cohort),
                       h3_cand(C["A"]), test)
    print(f"H3 [A] in-sample (fit on all A) for reference: {ins}; n_iter_={model_A.n_iter_}", flush=True)
    res.append(("H3 HGB poisson re-ranker", {"fit": "A (oof 5-fold for A score)", "n_iter": int(model_A.n_iter_)},
                mA, mB, tB + t_feat, comp_B))

    print("\n== HYBRIDS (tuned on A, reported on B)")
    print("| hybrid | params (from A) | A cohort | A test | B cohort | B test | cand. recall A | cand. recall B | mean cands B | runtime B: hybrid step (s) | runtime B: components (s) |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for name, p, a, b, t, tc in res:
        print(f"| {name} | {json.dumps(p)} | {a['cohort']:.5f} | {a['test']:.5f} | {b['cohort']:.5f} | {b['test']:.5f} | "
              f"{a['cand_recall']:.4f} | {b['cand_recall']:.4f} | {b['mean_cands']:.1f} | {t:.2f} | {tc:.2f} |")

    # ---------------- final
    best_name = max(res[1:], key=lambda r: r[2]["cohort"])[0]
    print(f"\nbest of H2/H3 by fold-A cohort MAP@5: {best_name}", flush=True)
    SF = Split("final", inter, unlab, eval_users=test_list)
    print(SF.describe(), flush=True)
    warm_t = [u for u in test_list if u in SF.hist]
    CF = Components(SF, warm_t, [a1])
    out = {}
    partial, _, mem = h1(CF, a1)
    out["H1"] = (score_lists(SF, partial, test_list), mem)
    partial, _, mem = h2(CF, h2_wide(CF), *w2)
    out["H2"] = (score_lists(SF, partial, test_list), mem)
    FF = h3_frame(CF)
    model_B = hgb().fit(FB[FEATURES], FB.label)
    print(f"H3 final: fit on B rows={len(FB)} (n_iter_={model_B.n_iter_}); final frame rows={len(FF)} users={FF.user_id.nunique()}")
    out["H3"] = (score_lists(SF, h3_lists(FF, model_B.predict(FF[FEATURES])), test_list), h3_members(CF))
    print("\n== SLOT SOURCES, final predictions for the 1260 test users (6300 slots; first matching source in "
          "priority order history > PPR > CBF > ALS > popularity, else fallback)")
    print("| hybrid | " + " | ".join(SLOT_SOURCES) + " |")
    print("|---|" + "---|" * len(SLOT_SOURCES))
    for h, (lists, mem) in out.items():
        c = slot_sources(lists, test_list, mem)
        print(f"| {h} | " + " | ".join(str(c[s]) for s in SLOT_SOURCES) + " |")
    for fname, key in [("s4_h1.csv", "H1"), ("s5_best_hybrid.csv", best_name.split()[0])]:
        path = SUB_DIR / fname
        write_submission(path, test_list, out[key][0])
        print(f"{fname} <- {key}")
        validate_submission(path, SF.pool_set)


if __name__ == "__main__":
    main()
