"""Step 5 part D: candidate recall (exposure source, top-60), per-week features, CatBoost YetiRank, seed bagging.
Everything selected on fold A (5-fold GroupKFold-by-user out-of-fold), reported on fold B (fit on all of A).
Final s7: fit on A+B stacked (DESIGN D50), applied to 11-30 -> 31-42.
Run: .venv/bin/python src/s5_push.py -> logs/s5_push.log, logs/s5_rows.csv
"""
import os

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")  # before numpy/sklearn load BLAS (BUGLOG B24)

import json
import time

import numpy as np
import pandas as pd
from catboost import CatBoostRanker, Pool
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold

import methods as M
import s4b_hybrids as H
import s4c_h3plus as P
from load import ART, ROOT, load_sub
from protocol import Split, load_interactions, load_unlab, mapk, window_mask
from s1_popularity import SUB_DIR, validate_submission, write_submission

TOP = 60
TRAIN_WEEKS = P.TRAIN_WEEKS                       # A 5, B 10, final 20
TARGET_WEEKS = {"A": 5, "B": 10, "final": 12}
BAG_SEEDS = [42, 43, 44, 45, 46]
CB_GRID = [(lr, d) for lr in [0.03, 0.1] for d in [4, 6, 8]]
CB_ITERS = 500
RAW = list(P.FEATURES_PLUS)
PW_MAP = {"n_pos": "n_pos_pw", "overlap_s": "overlap_pw", "pop": "pop_pw", "air_tr": "air_tr_pw",
          "air_t": "air_t_pw", "exp_all": "exp_all_pw", "exp_top3": "exp_top3_pw"}
FEATSETS = {"raw": RAW, "per-week": [PW_MAP.get(f, f) for f in RAW], "raw+per-week": RAW + list(PW_MAP.values())}
VARIANTS = {"current (5 sources, top-30)": (30, False), "+ exposure source (top-60), others top-30": (30, True),
            "+ exposure source, top-60 everywhere": (60, True)}
ROWS = []


class SplitData:
    def __init__(self, name, inter, unlab, pairs, eval_users=None, users=None):
        t = time.perf_counter()
        self.sd = sd = Split(name, inter, unlab, eval_users=eval_users)
        self.users = sd.warm if users is None else users
        self.C = H.Components(sd, self.users, [], topn=TOP)
        E, E3, ui, ii, info = P.exposure_matrices(sd, self.users, pairs)
        P._EXP_CACHE[(sd.name, len(self.users))] = (E, E3, ui, ii, info)
        self.exp_list = M.rank_lists(sd, self.users, sd.pool, E.toarray(), True, TOP)
        tw = pairs[window_mask(pairs, sd.train_windows) & pairs.user_id.isin(set(self.users)).values]
        self.active = tw.groupby("user_id").week.nunique()
        self.frames = {}
        self.build_s = time.perf_counter() - t
        print(f"[{name}] {sd.describe()} | components+exposure built in {self.build_s:.1f}s; exposure: {info}; "
              f"active train weeks per user: median={self.active.median()} min={self.active.min()} max={self.active.max()}",
              flush=True)

    def lists(self, topn, with_exp):
        L = {s: {u: l[:topn] for u, l in self.C.lists[s].items()} for s in self.C.lists}
        if with_exp:
            L["exposure"] = {u: l[:TOP] for u, l in self.exp_list.items()}
        return L

    def frame(self, variant, pairs):
        if variant not in self.frames:
            t = time.perf_counter()
            L = self.lists(*VARIANTS[variant])
            f = P.add_plus(H.h3_frame(self.C, L), self.C, pairs)
            aw = f.user_id.map(self.active).values.astype(float)
            n = self.sd.name
            f["n_pos_pw"], f["overlap_pw"] = f.n_pos / aw, f.overlap_s / aw
            f["pop_pw"], f["air_tr_pw"] = f["pop"] / TRAIN_WEEKS[n], f.air_tr / TRAIN_WEEKS[n]
            f["air_t_pw"] = f.air_t / TARGET_WEEKS[n]
            f["exp_all_pw"], f["exp_top3_pw"] = f.exp_all / TARGET_WEEKS[n], f.exp_top3 / TARGET_WEEKS[n]
            if "label" in f:
                f["label_pw"] = f.label / TARGET_WEEKS[n]
            self.frames[variant] = (f, L, time.perf_counter() - t)
        return self.frames[variant]


# ---------------------------------------------------------------- models
def fit_predict(model, Ftr, ytr, Fte, feats, seed):
    if model[0] == "hgb":
        m = HistGradientBoostingRegressor(loss="poisson", random_state=seed, learning_rate=0.01, max_iter=1000,
                                          categorical_features=[feats.index("category")])
        m.fit(Ftr[feats], ytr)
        return m.predict(Fte[feats])
    _, lr, depth = model
    o = np.argsort(Ftr.user_id.values, kind="stable")
    X = Ftr[feats].iloc[o].copy()
    X["category"] = X.category.astype(int).astype(str)
    gid = pd.factorize(Ftr.user_id.values[o])[0]
    m = CatBoostRanker(loss_function="YetiRank", learning_rate=lr, depth=depth, iterations=CB_ITERS,
                       random_seed=seed, verbose=0)
    m.fit(Pool(X, label=np.asarray(ytr)[o], group_id=gid, cat_features=["category"]))
    Xt = Fte[feats].copy()
    Xt["category"] = Xt.category.astype(int).astype(str)
    return m.predict(Pool(Xt, cat_features=["category"]))


def label_of(F, feats):
    return F.label_pw.values if feats is not RAW else F.label.values  # per-week label with per-week features


def run(name, DA, DB, test, variant, featset, model, seeds=(42,), pairs=None, eval_b=True):
    feats = FEATSETS[featset]
    FA, LA, tfa = DA.frame(variant, pairs)
    FB, LB, tfb = DB.frame(variant, pairs)
    yA = label_of(FA, feats)
    oof = np.zeros(len(FA))
    for s in seeds:
        for i_tr, i_te in GroupKFold(n_splits=5).split(FA, groups=FA.user_id):
            oof[i_te] += fit_predict(model, FA.iloc[i_tr], yA[i_tr], FA.iloc[i_te], feats, s) / len(seeds)
    mA = H.fold_metrics(DA.sd, H.score_lists(DA.sd, H.h3_lists(FA, oof), DA.sd.cohort), H.h3_cand(DA.C, LA), test)
    row = {"name": name, "variant": variant, "features": featset, "model": json.dumps(model), "seeds": len(seeds),
           "A_cohort": mA["cohort"], "A_test": mA["test"], "A_recall": mA["cand_recall"], "A_mean_cands": mA["mean_cands"]}
    if eval_b:
        t = time.perf_counter()
        pB = np.zeros(len(FB))
        for s in seeds:
            pB += fit_predict(model, FA, yA, FB, feats, s) / len(seeds)
        mB = H.fold_metrics(DB.sd, H.score_lists(DB.sd, H.h3_lists(FB, pB), DB.sd.cohort), H.h3_cand(DB.C, LB), test)
        row.update({"B_cohort": mB["cohort"], "B_test": mB["test"], "B_recall": mB["cand_recall"],
                    "B_mean_cands": mB["mean_cands"], "runtime_B_s": time.perf_counter() - t + tfb})
    ROWS.append(row)
    print("  " + " ".join(f"{k}={v:.5f}" if isinstance(v, float) else f"{k}={v}" for k, v in row.items()), flush=True)
    pd.DataFrame(ROWS).to_csv(ROOT / "logs" / "s5_rows.csv", index=False)
    return row


def main():
    inter, unlab = load_interactions(), load_unlab()
    test_list = load_sub().user_id.tolist()
    test = set(test_list)
    pairs = pd.read_parquet(ART / "view_airing_pairs.parquet",
                            columns=["user_id", "channel_id", "period", "week", "ov_start", "ov_end"])
    DA, DB = SplitData("A", inter, unlab, pairs), SplitData("B", inter, unlab, pairs)
    HGB = ("hgb",)
    base_variant, base_feats = list(VARIANTS)[0], "raw"

    print("\n== 1. candidate sources (H3+ HGB, raw features)", flush=True)
    r1 = {v: run(f"cands: {v}", DA, DB, test, v, "raw", HGB, pairs=pairs) for v in VARIANTS}
    base = r1[base_variant]
    ok = [v for v in VARIANTS if r1[v]["A_cohort"] >= base["A_cohort"]]
    cand_variant = max(ok, key=lambda v: r1[v]["A_recall"])
    print(f"-> candidate variant kept (max A recall with A MAP >= current {base['A_cohort']:.5f}): {cand_variant}")

    print("\n== 2. per-week features (current candidates, HGB)", flush=True)
    r2 = {fs: (base if fs == "raw" else run(f"features: {fs}", DA, DB, test, base_variant, fs, HGB, pairs=pairs))
          for fs in FEATSETS}
    feat_choice = max(FEATSETS, key=lambda fs: r2[fs]["A_cohort"])
    print(f"-> feature set kept (argmax A): {feat_choice}")

    print("\n== 4. CatBoostRanker YetiRank grid on A (current candidates, raw features)", flush=True)
    cb = {}
    for lr, d in CB_GRID:
        cb[(lr, d)] = run(f"catboost lr={lr} depth={d}", DA, DB, test, base_variant, "raw", ("cb", lr, d),
                          pairs=pairs, eval_b=False)
    lr, d = max(cb, key=lambda k: cb[k]["A_cohort"])
    CB = ("cb", lr, d)
    rcb = run(f"catboost lr={lr} depth={d} (selected)", DA, DB, test, base_variant, "raw", CB, pairs=pairs)
    model_choice = CB if rcb["A_cohort"] > base["A_cohort"] else HGB
    print(f"-> model kept (argmax A of HGB vs selected CatBoost): {model_choice}")

    print("\n== 5. seed bagging (5 seeds) of the best model on A", flush=True)
    rbag = run(f"bagging 5 seeds: {model_choice}", DA, DB, test, base_variant, "raw", model_choice, seeds=BAG_SEEDS,
               pairs=pairs)

    print("\n== 6. all kept changes together", flush=True)
    seeds_all = BAG_SEEDS if rbag["A_cohort"] > (rcb if model_choice == CB else base)["A_cohort"] else (42,)
    rall = run("all kept changes", DA, DB, test, cand_variant, feat_choice, model_choice, seeds=seeds_all, pairs=pairs)

    table = ([("H3+ (current)", base)]
             + [(f"candidates: {v}", r1[v]) for v in VARIANTS if v != base_variant]
             + [(f"features: {fs}", r2[fs]) for fs in FEATSETS if fs != "raw"]
             + [(f"model: CatBoost YetiRank lr={lr} depth={d}", rcb),
                (f"seed bagging x5 ({model_choice[0]})", rbag),
                (f"all kept changes together ({cand_variant}; {feat_choice}; {model_choice[0]}; seeds={len(seeds_all)})", rall)])
    print("\n== FINAL TABLE (A: OOF 5-fold by user; B: fit on all of A)")
    print("| config | A cohort | A test | B cohort | B test | cand. recall A | cand. recall B | runtime B (s) |")
    print("|---|---|---|---|---|---|---|---|")
    for label, r in table:
        print(f"| {label} | {r['A_cohort']:.5f} | {r['A_test']:.5f} | {r['B_cohort']:.5f} | {r['B_test']:.5f} | "
              f"{r['A_recall']:.4f} | {r['B_recall']:.4f} | {r['runtime_B_s']:.1f} |")
    print("CatBoost grid (A OOF cohort): " + ", ".join(f"lr={k[0]} d={k[1]}: {v['A_cohort']:.5f}" for k, v in cb.items()))

    best_label, best = max(table, key=lambda x: x[1]["A_cohort"])
    print(f"\nbest fold-A config: {best_label}: variant={best['variant']} features={best['features']} "
          f"model={best['model']} seeds={best['seeds']}", flush=True)
    final_s7(inter, unlab, pairs, test_list, DA, DB, best)


def final_s7(inter, unlab, pairs, test_list, DA, DB, best):
    """DESIGN D50: fit on A+B stacked with per-week label, apply to 11-30 -> 31-42."""
    variant, feats = best["variant"], FEATSETS[best["features"]]
    model = tuple(json.loads(best["model"]))
    seeds = BAG_SEEDS if best["seeds"] == 5 else [42]
    sf = Split("final", inter, unlab, eval_users=test_list)
    DF = SplitData("final", inter, unlab, pairs, eval_users=test_list, users=[u for u in test_list if u in sf.hist])
    FA, _, _ = DA.frame(variant, pairs)
    FB, _, _ = DB.frame(variant, pairs)
    FF, LF, _ = DF.frame(variant, pairs)
    Ftr = pd.concat([FA, FB], ignore_index=True)
    ytr = Ftr.label_pw.values
    pred = np.zeros(len(FF))
    for s in seeds:
        pred += fit_predict(model, Ftr, ytr, FF, feats, s) / len(seeds)
    lists = H.score_lists(DF.sd, H.h3_lists(FF, pred), test_list)
    print(f"[final] fit on A+B stacked: rows={len(Ftr)} (A {len(FA)}, B {len(FB)}), label = positives per target week; "
          f"final frame rows={len(FF)} users={FF.user_id.nunique()}")
    c = H.slot_sources(lists, test_list, H.h3_members(DF.C, LF))
    print("\n== s7 SLOT SOURCES (1260 test users, 6300 slots; priority history > PPR > CBF > ALS > exposure > "
          "popularity, else fallback)")
    print("| " + " | ".join(H.SLOT_SOURCES) + " |")
    print("|" + "---|" * len(H.SLOT_SOURCES))
    print("| " + " | ".join(str(c[s]) for s in H.SLOT_SOURCES) + " |")
    path = SUB_DIR / "s7_best.csv"
    write_submission(path, test_list, lists)
    validate_submission(path, DF.sd.pool_set)


if __name__ == "__main__":
    main()
