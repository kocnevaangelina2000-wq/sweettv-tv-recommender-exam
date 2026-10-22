"""Step 4 part A: every method grid on fold A and fold B; params selected on fold A only, reported on fold B.
Then final single-method submissions (train 11-30 -> 31-42) with fold-A params.
Run: .venv/bin/python src/s4a_folds.py  -> logs/s4a_folds.log, logs/s4a_grid.csv, logs/s4a_selected.json
"""
import itertools
import json
import time

import numpy as np
import pandas as pd

import methods as M
from load import ROOT, load_sub
from protocol import Split, check_lists, load_interactions, load_unlab, mapk
from s1_popularity import SUB_DIR, validate_submission, write_submission

ALS_GRID = list(itertools.product(["count", "log1p", "bm25"], [8, 16, 32, 64, 128], [0.01, 0.1],
                                  [0.1, 0.3, 1, 10, 40]))
PPR_ALPHAS = [0.3, 0.5, 0.7, 0.85]
ROWS = []


def evaluate(sd, cohort_test, method, params, partial, runtime, extra=None):
    lists = sd.finish(partial)
    check_lists(lists, sd.pool_set)
    row = {"fold": sd.name, "method": method, "params": json.dumps(params, sort_keys=True),
           "map5_cohort": mapk(lists, sd.truth, sd.cohort), "map5_test": mapk(lists, sd.truth, cohort_test),
           "rewatch_share": float(np.mean([len(set(l) & sd.hist.get(u, set())) / 5 for u, l in lists.items()])),
           "runtime_s": runtime, **(extra or {})}
    ROWS.append(row)
    print(f"  [{sd.name}] {method:<24} {row['params']:<62} cohort={row['map5_cohort']:.5f} "
          f"test={row['map5_test']:.5f} rw={row['rewatch_share']:.3f} t={runtime:.2f}s" + (f" {extra}" if extra else ""),
          flush=True)


def run_fold(sd, test):
    ct = [u for u in sd.cohort if u in test]
    warm = [u for u in sd.cohort if u in sd.hist]
    print(sd.describe(), f"| test subset={len(ct)}", flush=True)
    t = time.perf_counter()
    glob = sd.pop.tv_show_id.head(5).tolist()
    evaluate(sd, ct, "popularity", {}, {u: glob for u in warm}, time.perf_counter() - t)

    for variant, hs in [("count", [None]), ("recency", [2, 4]), ("expected", [None])]:
        for h in hs:
            t = time.perf_counter()
            p = M.history_lists(sd, variant, h)
            evaluate(sd, ct, f"history {variant}", {} if h is None else {"half_life_w": h}, p, time.perf_counter() - t)

    for conf, f, reg, a in ALS_GRID:
        t = time.perf_counter()
        items, S = M.als_scores(sd, warm, conf, f, reg, a)
        t_fit = time.perf_counter() - t
        params = {"conf": conf, "factors": f, "reg": reg, "alpha": a}
        for name, Sv in [("ALS", S), ("ALS x air", S * M.air_weight(sd, items))]:
            t = time.perf_counter()
            evaluate(sd, ct, name, params, M.rank_lists(sd, warm, items, Sv, False), t_fit + time.perf_counter() - t)

    print("  " + M.ppr_mass_checks(sd), flush=True)
    for a in PPR_ALPHAS:
        t = time.perf_counter()
        items, S, conv = M.ppr_scores(sd, warm, a)
        t_fit = time.perf_counter() - t
        for name, Sv in [("PPR", S), ("PPR x air", S * M.air_weight(sd, items))]:
            t = time.perf_counter()
            evaluate(sd, ct, name, {"alpha": a}, M.rank_lists(sd, warm, items, Sv, True),
                     t_fit + time.perf_counter() - t, conv)

    t = time.perf_counter()
    items, S, info = M.cbf_scores(sd, warm)
    t_fit = time.perf_counter() - t
    print(f"  content: {info}")
    for name, Sv in [("CBF", S), ("CBF x air", S * M.air_weight(sd, items))]:
        t = time.perf_counter()
        evaluate(sd, ct, name, {}, M.rank_lists(sd, warm, items, Sv, True), t_fit + time.perf_counter() - t)


def select(g):
    """Per method: params with the best fold-A cohort MAP@5 (first in grid order on ties); fold-B value of the
    same params; plus fold-B best-of-grid (oracle, reference only)."""
    out, sel = [], {}
    for method in g.method.unique():
        a = g[(g.fold == "A") & (g.method == method)]
        b = g[(g.fold == "B") & (g.method == method)]
        ra = a.loc[a.map5_cohort.idxmax()]
        rb = b[b.params == ra.params].iloc[0]
        ob = b.loc[b.map5_cohort.idxmax()]
        sel[method] = json.loads(ra.params)
        out.append({"method": method, "params (chosen on A)": ra.params, "n grid": len(a),
                    "A cohort": ra.map5_cohort, "A test": ra.map5_test, "B cohort": rb.map5_cohort,
                    "B test": rb.map5_test, "B rewatch": rb.rewatch_share, "B runtime_s": rb.runtime_s,
                    "B oracle cohort": ob.map5_cohort, "B oracle params": ob.params})
    return pd.DataFrame(out), sel


def final_submissions(inter, unlab, test_list, sel):
    sd = Split("final", inter, unlab, eval_users=test_list)
    print(sd.describe(), flush=True)
    warm = [u for u in test_list if u in sd.hist]
    t = time.perf_counter()
    lists = sd.finish(M.history_lists(sd, "count"))
    check_lists(lists, sd.pool_set)
    path = SUB_DIR / "s2_history.csv"
    write_submission(path, test_list, lists)
    print(f"[final] history count: {time.perf_counter() - t:.2f}s")
    validate_submission(path, sd.pool_set)
    a = sel["PPR x air"]["alpha"]
    t = time.perf_counter()
    items, S, conv = M.ppr_scores(sd, warm, a)
    lists = sd.finish(M.rank_lists(sd, warm, items, S * M.air_weight(sd, items), True))
    check_lists(lists, sd.pool_set)
    path = SUB_DIR / "s3_ppr_air.csv"
    write_submission(path, test_list, lists)
    print(f"[final] PPR x air alpha={a}: {time.perf_counter() - t:.2f}s {conv}; " + M.ppr_mass_checks(sd))
    validate_submission(path, sd.pool_set)


def main():
    inter, unlab = load_interactions(), load_unlab()
    test_list = load_sub().user_id.tolist()
    test = set(test_list)
    for fold in ["A", "B"]:
        run_fold(Split(fold, inter, unlab), test)
    g = pd.DataFrame(ROWS)
    g.to_csv(ROOT / "logs" / "s4a_grid.csv", index=False)
    table, sel = select(g)
    (ROOT / "logs" / "s4a_selected.json").write_text(json.dumps(sel, indent=1))
    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 80)
    print("\n== SELECTION (params chosen on fold A, reported on fold B)")
    print(table.to_string(index=False, float_format=lambda x: f"{x:.5f}"))
    final_submissions(inter, unlab, test_list, sel)


if __name__ == "__main__":
    main()
