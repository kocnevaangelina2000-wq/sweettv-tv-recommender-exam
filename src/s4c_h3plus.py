"""Step 4 part C: H3+ = H3 + features that follow how Kaggle counts (positive airings).
exposure (hour-of-week watch probability x target airings), programme length / positive rate.
Title-transfer features are not added: logs/check_title_transfer.log shows < 1% of truth items (DESIGN D45).
Run: .venv/bin/python src/s4c_h3plus.py -> logs/s4c_h3plus.log
"""
import os

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")  # before numpy/sklearn load BLAS (BUGLOG B24)

import time

import numpy as np
import pandas as pd
import scipy.sparse as sp
from sklearn.model_selection import GroupKFold

import s4b_hybrids as H
from load import ART, load_sub
from protocol import Split, channel_share, load_interactions, load_unlab, mapk, user_programme_stats, window_mask
from s1_popularity import SUB_DIR, validate_submission, write_submission

TRAIN_WEEKS = {"A": 5, "B": 10, "final": 20}
GROUPS = {
    "history": ["n_pos", "overlap_s", "last_week_ago", "share_pos"],
    "graph/ALS/content scores": ["ppr", "ppr_rank", "als", "als_rank", "cbf", "cbf_rank"],
    "exposure": ["exp_all", "exp_top3", "chan_share"],
    "popularity/airings": ["pop", "air_t", "air_tr"],
    "length": ["med_dur", "pos_rate"],
}
FEATURES_PLUS = H.FEATURES + ["exp_all", "exp_top3", "med_dur", "pos_rate"]
HOW = 168  # hours in a week


def how_of(epoch_s):
    """Hour-of-week (Mon 00:00 = 0) and Monday-based week id from naive wall-clock epoch seconds."""
    hours = epoch_s // 3600
    days = hours // 24
    return ((days + 3) % 7) * 24 + hours % 24, (days + 3) // 7  # 1970-01-01 is a Thursday


def watch_prob(sd, pairs):
    """P(u, channel, hour-of-week) = share of train weeks in which u had overlap > 0 with that channel in
    that hour (labelled + id=0 airtime). Returns DataFrame user_id, key, p with key = channel*168 + how."""
    p = pairs[window_mask(pairs, sd.train_windows)]
    h0 = p.ov_start.values // 3600
    h1 = (p.ov_end.values - 1) // 3600
    n = (h1 - h0 + 1).astype(np.int64)
    idx = np.repeat(np.arange(len(p)), n)
    hours = np.repeat(h0, n) + (np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n))
    how, wk = how_of(hours * 3600)
    d = pd.DataFrame({"user_id": p.user_id.values[idx], "key": p.channel_id.values[idx].astype(np.int64) * HOW + how,
                      "wk": wk}).drop_duplicates()
    out = d.groupby(["user_id", "key"]).size().rename("weeks").reset_index()
    out["p"] = np.minimum(1.0, out.weeks / TRAIN_WEEKS[sd.name])
    return out, len(p), int(n.sum())


def exposure_matrices(sd, users, pairs):
    """E (users x pool) = Σ over each programme's target-window airings of P(u, channel, how of airing start);
    E3 = the same with P restricted to u's top-3 channels by train seconds. Rows = users, cols = sd.pool."""
    P, n_pieces, n_slots = watch_prob(sd, pairs)
    P = P[P.user_id.isin(set(users))]
    s = sd.pool_sched
    how, _ = how_of(s.start_time.values.astype("datetime64[s]").astype(np.int64))
    N = pd.DataFrame({"tv_show_id": s.tv_show_id.values, "key": s.channel_id.values.astype(np.int64) * HOW + how})
    N = N.groupby(["tv_show_id", "key"]).size().rename("n").reset_index()
    keys = pd.Index(sorted(set(P.key) | set(N.key)))
    ui, ii = pd.Index(users), pd.Index(sd.pool)
    Pm = sp.csr_matrix((P.p.values, (ui.get_indexer(P.user_id), keys.get_indexer(P.key))), shape=(len(ui), len(keys)))
    Nm = sp.csr_matrix((N.n.values.astype(float), (ii.get_indexer(N.tv_show_id), keys.get_indexer(N.key))),
                       shape=(len(ii), len(keys)))
    cs = channel_share(users, sd.tr, sd.unlab_tr).sort_values(["user_id", "share"], ascending=[True, False])
    top3 = cs.groupby("user_id").head(3)
    P3 = P.merge(top3[["user_id", "channel_id"]].rename(columns={"channel_id": "ch"}), on="user_id")
    P3 = P3[P3.key // HOW == P3.ch]
    P3m = sp.csr_matrix((P3.p.values, (ui.get_indexer(P3.user_id), keys.get_indexer(P3.key))), shape=Pm.shape)
    info = f"train pieces={n_pieces} hour slots={n_slots} P rows={len(P)} keys={len(keys)}"
    return (Pm @ Nm.T).tocsr(), (P3m @ Nm.T).tocsr(), ui, ii, info


_EXP_CACHE = {}


def exposure(sd, users, cand, pairs):
    key = (sd.name, len(users))
    if key not in _EXP_CACHE:
        _EXP_CACHE[key] = exposure_matrices(sd, users, pairs)
    E, E3, ui, ii, info = _EXP_CACHE[key]
    r, c = ui.get_indexer(cand.user_id), ii.get_indexer(cand.tv_show_id)
    assert (r >= 0).all() and (c >= 0).all()
    return np.asarray(E[r, c]).ravel(), np.asarray(E3[r, c]).ravel(), info


def add_plus(f, C, pairs):
    sd = C.sd
    f = f.copy()
    t = time.perf_counter()
    f["exp_all"], f["exp_top3"], info = exposure(sd, C.users, f, pairs)
    f["med_dur"] = f.tv_show_id.map(sd.pool_sched.groupby("tv_show_id").duration.median()).values
    seen = sd.tr.groupby(["user_id", "tv_show_id"]).size()
    n_seen = seen.reindex(pd.MultiIndex.from_frame(f[["user_id", "tv_show_id"]])).values
    f["pos_rate"] = np.where(n_seen > 0, f.n_pos.values / np.where(n_seen > 0, n_seen, 1), np.nan)
    print(f"   [{sd.name}] H3+ features in {time.perf_counter() - t:.1f}s; exposure: {info}; "
          f"exp_all>0 share={(f.exp_all > 0).mean():.3f}", flush=True)
    return f


def oof_lists(F, feats):
    oof = np.zeros(len(F))
    for i_tr, i_te in GroupKFold(n_splits=5).split(F, groups=F.user_id):
        oof[i_te] = H.hgb_for(feats).fit(F.iloc[i_tr][feats], F.iloc[i_tr].label).predict(F.iloc[i_te][feats])
    return H.h3_lists(F, oof)


def main():
    inter, unlab = load_interactions(), load_unlab()
    test_list = load_sub().user_id.tolist()
    test = set(test_list)
    pairs = pd.read_parquet(ART / "view_airing_pairs.parquet",
                            columns=["user_id", "channel_id", "period", "week", "ov_start", "ov_end"])
    S, C, F = {}, {}, {}
    for f in ["A", "B"]:
        S[f] = Split(f, inter, unlab)
        C[f] = H.Components(S[f], S[f].warm, [])
        F[f] = add_plus(H.h3_frame(C[f]), C[f], pairs)
    rows, lists_B = [], {}
    for name, feats in [("H3", H.FEATURES), ("H3+", FEATURES_PLUS)]:
        t = time.perf_counter()
        mA = H.fold_metrics(S["A"], H.score_lists(S["A"], oof_lists(F["A"], feats), S["A"].cohort), H.h3_cand(C["A"]), test)
        model = H.hgb_for(feats).fit(F["A"][feats], F["A"].label)
        lB = H.score_lists(S["B"], H.h3_lists(F["B"], model.predict(F["B"][feats])), S["B"].cohort)
        mB = H.fold_metrics(S["B"], lB, H.h3_cand(C["B"]), test)
        lists_B[name] = lB
        rows.append((name, len(feats), mA, mB, time.perf_counter() - t))
        print(f"{name}: A(oof)={mA} B={mB}", flush=True)
    print("\n== H3 vs H3+ (A: 5-fold grouped out-of-fold; B: fit on all of A)")
    print("| model | #features | A cohort | A test | B cohort | B test | cand. recall A | cand. recall B | fit+predict time (s) |")
    print("|---|---|---|---|---|---|---|---|---|")
    for name, nf, a, b, t in rows:
        print(f"| {name} | {nf} | {a['cohort']:.5f} | {a['test']:.5f} | {b['cohort']:.5f} | {b['test']:.5f} | "
              f"{a['cand_recall']:.4f} | {b['cand_recall']:.4f} | {t:.1f} |")

    full_B = rows[1][3]
    ct = [u for u in S["B"].cohort if u in test]
    print("\n== ABLATION on fold B (H3+, fit on A without the group, evaluated on B)")
    print("| dropped group | features dropped | B cohort | drop vs H3+ | B test | drop vs H3+ |")
    print("|---|---|---|---|---|---|")
    for g, cols in list(GROUPS.items()) + [("title", [])]:
        if not cols:
            print("| title | — (not added: < 1% of truth items, logs/check_title_transfer.log) | — | — | — | — |")
            continue
        feats = [x for x in FEATURES_PLUS if x not in cols]
        model = H.hgb_for(feats).fit(F["A"][feats], F["A"].label)
        l = H.score_lists(S["B"], H.h3_lists(F["B"], model.predict(F["B"][feats])), S["B"].cohort)
        mc, mt = mapk(l, S["B"].truth, S["B"].cohort), mapk(l, S["B"].truth, ct)
        print(f"| {g} | {', '.join(cols)} | {mc:.5f} | {full_B['cohort'] - mc:+.5f} | {mt:.5f} | {full_B['test'] - mt:+.5f} |",
              flush=True)

    if rows[1][3]["cohort"] > rows[0][3]["cohort"]:
        SF = Split("final", inter, unlab, eval_users=test_list)
        CF = H.Components(SF, [u for u in test_list if u in SF.hist], [])
        FF = add_plus(H.h3_frame(CF), CF, pairs)
        model = H.hgb_for(FEATURES_PLUS).fit(F["B"][FEATURES_PLUS], F["B"].label)
        lists = H.score_lists(SF, H.h3_lists(FF, model.predict(FF[FEATURES_PLUS])), test_list)
        print(f"\nH3+ beats H3 on fold B cohort -> final: fit on B (rows={len(F['B'])}, n_iter_={model.n_iter_}), "
              f"final frame rows={len(FF)}")
        c = H.slot_sources(lists, test_list, H.h3_members(CF))
        print("slot sources (final, 1260 test users): " + ", ".join(f"{k}={v}" for k, v in c.items()))
        path = SUB_DIR / "s6_h3plus.csv"
        write_submission(path, test_list, lists)
        validate_submission(path, SF.pool_set)
    else:
        print("\nH3+ does not beat H3 on fold B cohort -> no s6 file")


if __name__ == "__main__":
    main()
