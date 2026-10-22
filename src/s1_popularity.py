"""Step 2: protocol report + popularity baseline (validation and final submission).
Run: .venv/bin/python src/s1_popularity.py
"""
import numpy as np
import pandas as pd

from load import DATA, ROOT, SUB_FILE, load_sub
from protocol import THR, Split, channel_fallback, check_lists, load_interactions, load_unlab, mapk

SUB_DIR = ROOT / "submissions"
SUB_DIR.mkdir(exist_ok=True)


def pool_report(name, pool_sched):
    a = pool_sched.groupby("tv_show_id").size()
    title = pool_sched.groupby("tv_show_id").tv_show_title.agg(lambda s: s.value_counts().index[0])
    cat = pool_sched.groupby("tv_show_id").tv_show_category.first()
    print(f"[{name}] pool size={a.size} programmes; airings per programme: median={a.median()} mean={a.mean():.2f} "
          f"p90={a.quantile(.9)} max={a.max()}; programmes airing once: {(a == 1).sum()}")
    top = a.sort_values(ascending=False).head(10)
    for pid, n in top.items():
        print(f"    {pid:>10}  airings={n:>4}  [{cat[pid]}]  {title[pid]}")


def predict(users, train_inter, unlab_train, pool_sched, pop, with_fallback):
    glob = pop.tv_show_id.head(5).tolist()
    has_pos = set(train_inter.user_id[train_inter.screen_time >= THR])
    warm = [u for u in users if u in has_pos]
    cold = [u for u in users if u not in has_pos]
    preds = {u: list(glob) for u in warm}
    if with_fallback:
        preds.update(channel_fallback(cold, train_inter, unlab_train, pool_sched, pop))
    else:
        preds.update({u: list(glob) for u in cold})
    return preds, len(warm), len(cold)


def main():
    inter, unlab = load_interactions(), load_unlab()
    test = load_sub().user_id.tolist()
    test_set = set(test)

    # ---------------- validation (split B) ----------------
    sd = Split("B", inter, unlab)
    tr, truth, cohort = sd.tr, sd.truth, sd.cohort
    all_users = set(inter.user_id)  # users with >=1 joined labelled view in 11-30
    train_pos_users = set(sd.hist)
    cohort_test = [u for u in cohort if u in test_set]
    print("== VALIDATION COHORT (train 11-20 -> truth 21-30)")
    print(f"evaluable users (>=1 positive in 21-30): {len(cohort)}; users with labelled interactions in 11-30 but no truth: "
          f"{len(all_users - set(cohort))}; evaluable users with no positives in 11-20: {len(set(cohort) - train_pos_users)}")
    print(f"test users: {len(test)}; evaluable: {len(cohort_test)}; no truth: {len(test_set - set(cohort))}; "
          f"evaluable with no positives in 11-20: {len(set(cohort_test) - train_pos_users)}")
    tl = pd.Series([len(t) for t in truth.values()])
    print(f"truth length distribution (all cohort): {tl.value_counts().sort_index().to_dict()}")

    pool_sched, pool_ids, pop = sd.pool_sched, sd.pool_set, sd.pop
    out = sum(1 for t in truth.values() for p in t if p not in pool_ids)
    print(f"[val] truth programme slots outside the 21-30 pool: {out} of {int(tl.sum())}; "
          f"distinct truth programmes: {len({p for t in truth.values() for p in t})}")
    pool_report("val 21-30", pool_sched)
    print("[val] global popularity top-5 (n_pos in 11-20):",
          pop.head(5)[["tv_show_id", "n_pos"]].to_dict("records"))
    print(f"[val] pool programmes with 0 positives in train: {(pop.n_pos == 0).sum()} of {len(pop)}")
    for fb in [False, True]:
        preds, nw, nc = predict(cohort, tr, sd.unlab_tr, pool_sched, pop, fb)
        check_lists(preds, pool_ids)
        cold = [u for u in cohort if u not in train_pos_users]
        cold_t = [u for u in cohort_test if u not in train_pos_users]
        print(f"[val] popularity {'WITH' if fb else 'WITHOUT'} channel fallback: MAP@5 cohort={mapk(preds, truth, cohort):.5f} "
              f"(n={len(cohort)}) test-subset={mapk(preds, truth, cohort_test):.5f} (n={len(cohort_test)}) | "
              f"cold-only cohort={mapk(preds, truth, cold):.5f} (n={len(cold)}) cold-only test={mapk(preds, truth, cold_t) if cold_t else float('nan'):.5f} (n={len(cold_t)})")

    # ---------------- final ----------------
    sd = Split("final", inter, unlab, eval_users=test)
    tr, pool_sched, pool_ids, pop = sd.tr, sd.pool_sched, sd.pool_set, sd.pop
    pool_report("final 31-42", pool_sched)
    print("[final] global popularity top-5 (n_pos in 11-30):",
          pop.head(5)[["tv_show_id", "n_pos"]].to_dict("records"))
    preds, nw, nc = predict(test, tr, sd.unlab_tr, pool_sched, pop, True)
    check_lists(preds, pool_ids)
    print(f"[final] test users with positives in 11-30: {nw}; fallback users: {nc}")
    path = SUB_DIR / "s1_popularity.csv"
    write_submission(path, test, preds)
    validate_submission(path, pool_ids)


def write_submission(path, users, preds):
    pd.DataFrame({"user_id": [str(u) for u in users],
                  "tv_show_id": [" ".join(map(str, preds[u])) for u in users]}).to_csv(path, index=False)


def validate_submission(path, pool_ids):
    tmpl = pd.read_csv(DATA / SUB_FILE, dtype=str)
    sub = pd.read_csv(path, dtype=str)
    with open(path) as f:
        n_lines = sum(1 for _ in f)
    ok = {
        "header == template header": list(sub.columns) == list(tmpl.columns),
        "1260 rows + header": len(sub) == 1260 and n_lines == 1261,
        "user order == template": sub.user_id.tolist() == tmpl.user_id.tolist(),
        "5 unique ids per row": sub.tv_show_id.str.split(" ").map(lambda l: len(l) == 5 and len(set(l)) == 5).all(),
        "all ids integers in 31-42 pool": sub.tv_show_id.str.split(" ").map(
            lambda l: all(x.isdigit() and int(x) in pool_ids for x in l)).all(),
    }
    for k, v in ok.items():
        print(f"[submission check] {k}: {v}")
    assert all(ok.values())
    print(f"wrote {path.relative_to(ROOT)}; distinct lists: {sub.tv_show_id.nunique()}; first rows:\n{sub.head(3).to_string(index=False)}")


if __name__ == "__main__":
    main()
