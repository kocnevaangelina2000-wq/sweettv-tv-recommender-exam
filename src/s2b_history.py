"""s2b: history-by-count with ties broken by global popularity (the tie-break that wins on fold A,
logs/check_history_ties.log), final split 11-30 -> 31-42.
Run: .venv/bin/python src/s2b_history.py -> logs/s2b_history.log
"""
import pandas as pd

import methods as M
from load import load_sub
from protocol import Split, check_lists, load_interactions, load_unlab, mapk
from s1_popularity import SUB_DIR, validate_submission, write_submission


def main():
    inter, unlab = load_interactions(), load_unlab()
    test_list = load_sub().user_id.tolist()
    test = set(test_list)
    for fold in ["A", "B"]:  # reproduce check_history_ties through the library function
        sd = Split(fold, inter, unlab)
        ct = [u for u in sd.cohort if u in test]
        for ties in ["seconds", "popularity"]:
            l = sd.finish(M.history_lists(sd, "count", ties=ties))
            print(f"[{fold}] history count, ties by {ties}: cohort={mapk(l, sd.truth, sd.cohort):.5f} "
                  f"test={mapk(l, sd.truth, ct):.5f}")
    sd = Split("final", inter, unlab, eval_users=test_list)
    lists = sd.finish(M.history_lists(sd, "count", ties="popularity"))
    check_lists(lists, sd.pool_set)
    path = SUB_DIR / "s2b_history.csv"
    write_submission(path, test_list, lists)
    validate_submission(path, sd.pool_set)
    old = pd.read_csv(SUB_DIR / "s2_history.csv", dtype=str)
    new = pd.read_csv(path, dtype=str)
    same_set = (old.tv_show_id.str.split().map(frozenset) == new.tv_show_id.str.split().map(frozenset)).sum()
    print(f"vs s2_history.csv: identical rows {(old.tv_show_id == new.tv_show_id).sum()} of {len(new)}; "
          f"same 5 ids (any order) {same_set} of {len(new)}")


if __name__ == "__main__":
    main()
