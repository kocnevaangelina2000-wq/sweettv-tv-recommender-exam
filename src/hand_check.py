"""Hand-check pack: one fold-B cohort user from the 1260 test users with 5 truth programmes and s7-config
fold-B AP@5 in [0.3, 0.8] (seed 42 pick). Writes analysis/hand_check_*.csv (raw rows only for part a).
The s7 config on fold B = CatBoost YetiRank lr 0.03 depth 8, seeds 42-46, current candidates, raw features,
fit on fold A (the "seed bagging x5" row of logs/s5_push.log).
Run: .venv/bin/python src/hand_check.py -> logs/hand_check.log
"""
import os

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")  # before numpy/sklearn load BLAS (BUGLOG B24)

import numpy as np
import pandas as pd

import s4b_hybrids as H
import s5_push as S5
from load import ART, DATA, LOG_FILE, ROOT, SCHED_FILES, load_sub
from protocol import THR, apk, load_interactions, load_unlab, mapk, user_programme_stats

OUT = ROOT / "analysis"
OUT.mkdir(exist_ok=True)
TARGET_PERIOD = "21-30"
MAX_LOG_ROWS = 40  # part a) must stay small enough to do by hand


def model_lists():
    inter, unlab = load_interactions(), load_unlab()
    test = set(load_sub().user_id.tolist())
    pairs = pd.read_parquet(ART / "view_airing_pairs.parquet",
                            columns=["user_id", "channel_id", "period", "week", "ov_start", "ov_end"])
    DA, DB = S5.SplitData("A", inter, unlab, pairs), S5.SplitData("B", inter, unlab, pairs)
    v = list(S5.VARIANTS)[0]
    FA, _, _ = DA.frame(v, pairs)
    FB, _, _ = DB.frame(v, pairs)
    p = np.zeros(len(FB))
    for s in S5.BAG_SEEDS:
        p += S5.fit_predict(("cb", 0.03, 8), FA, FA.label.values, FB, S5.RAW, s) / len(S5.BAG_SEEDS)
    sd = DB.sd
    lists = H.score_lists(sd, H.h3_lists(FB, p), sd.cohort)
    ct = [u for u in sd.cohort if u in test]
    print(f"s7 config on fold B: cohort={mapk(lists, sd.truth, sd.cohort):.5f} test={mapk(lists, sd.truth, ct):.5f} "
          f"(logs/s5_push.log bagging row: 0.35415 / 0.39646)", flush=True)
    return inter, sd, lists, ct


def main():
    inter, sd, lists, ct = model_lists()
    elig = sorted(u for u in ct if len(sd.truth[u]) == 5 and 0.3 <= apk(lists[u], sd.truth[u]) <= 0.8)
    u = elig[np.random.default_rng(42).integers(len(elig))]
    print(f"eligible users (test, fold-B cohort, 5 truth programmes, 0.3 <= AP@5 <= 0.8): {len(elig)}; picked {u}")

    # ---- raw rows, read as strings straight from the csv files
    log = pd.read_csv(DATA / LOG_FILE, dtype=str, keep_default_na=False)
    log.insert(0, "csv_line", np.arange(len(log)) + 2)  # 1-based line in the file (line 1 = header)
    ulog = log[log.user_id == str(u)]
    sch = pd.read_csv(DATA / SCHED_FILES[TARGET_PERIOD], dtype=str, keep_default_na=False)
    sch.insert(0, "csv_line", np.arange(len(sch)) + 2)

    # independent overlap from the raw strings: same channel, [start, stop) x [start, start + duration)
    v0 = pd.to_datetime(ulog.start_time, format="%Y-%m-%d %H:%M:%S").values
    v1 = pd.to_datetime(ulog.stop_time, format="%Y-%m-%d %H:%M:%S").values
    vch = ulog.vsetv_id.astype(int).values
    tg = inter[(inter.user_id == u) & (inter.period == TARGET_PERIOD)]
    cand = []
    for p in sd.truth[u]:
        s = sch[sch.tv_show_id == str(p)]
        a0 = pd.to_datetime(s.start_time, format="%d.%m.%Y %H:%M:%S").values
        a1 = a0 + pd.to_timedelta(s.duration.astype(int).values, unit="s").values
        ov = ((vch[:, None] == s.channel_id.astype(int).values[None, :]) & (v0[:, None] < a1[None, :])
              & (v1[:, None] > a0[None, :]) & (s.duration.astype(int).values[None, :] > 0))
        rows, airs = ulog[ov.any(1)], s[ov.any(0)]
        # recompute positives from the raw rows (union of clipped pieces per airing) and compare with the code
        n_pos = 0
        for j in np.flatnonzero(ov.any(0)):
            i = np.flatnonzero(ov[:, j])
            pieces = sorted(zip(np.maximum(v0[i], a0[j]), np.minimum(v1[i], a1[j])))
            tot, cur_s, cur_e = 0, None, None
            for ps, pe in pieces:
                if cur_e is None or ps > cur_e:
                    tot += 0 if cur_e is None else (cur_e - cur_s) / np.timedelta64(1, "s")
                    cur_s, cur_e = ps, pe
                else:
                    cur_e = max(cur_e, pe)
            tot += (cur_e - cur_s) / np.timedelta64(1, "s")
            n_pos += min(1.0, tot / int(s.duration.values[j])) >= THR
        t = tg[tg.tv_show_id == p]
        code_pos = int((t.screen_time >= THR).sum())
        cand.append({"p": p, "rows": rows, "airs": airs, "n_pos_raw": n_pos, "n_pos_code": code_pos,
                     "airings_code": len(t), "below": len(airs) - n_pos})
    # part a) programme: >= 2 positives and >= 1 overlapped airing below 0.8 if any, then fewest log rows
    ok = [c for c in cand if len(c["rows"]) <= MAX_LOG_ROWS]
    pref = [c for c in ok if c["n_pos_raw"] >= 2 and c["below"] >= 1] or [c for c in ok if c["n_pos_raw"] >= 2] or ok
    c = min(pref, key=lambda c: len(c["rows"]))
    # printed without values on purpose: the user computes part a) by hand
    print(f"part a) programme {c['p']}: log rows={len(c['rows'])}, airings={len(c['airs'])}; independent raw "
          f"recompute == code: positives {c['n_pos_raw'] == c['n_pos_code']}, overlapped airings "
          f"{len(c['airs']) == c['airings_code']}")
    print("independent raw recompute == code for all 5 truth programmes: "
          f"{all(x['n_pos_raw'] == x['n_pos_code'] and len(x['airs']) == x['airings_code'] for x in cand)}")
    c["rows"].to_csv(OUT / "hand_check_a_log_rows.csv", index=False)
    c["airs"].to_csv(OUT / "hand_check_a_schedule_rows.csv", index=False)

    # ---- b) full truth table 21-30
    up = user_programme_stats(tg)
    up = up[up.n_pos >= 1].sort_values(["n_pos", "overlap_s", "tv_show_id"], ascending=[False, False, True])
    title = sd.pool_sched.groupby("tv_show_id").tv_show_title.agg(lambda x: x.value_counts().index[0])
    b = pd.DataFrame({"rank": np.arange(1, len(up) + 1), "tv_show_id": up.tv_show_id.values,
                      "title": up.tv_show_id.map(title).values, "positive_count": up.n_pos.values,
                      "total_seconds": up.overlap_s.values, "in_truth_top5": np.arange(len(up)) < 5})
    assert b.tv_show_id.head(5).tolist() == sd.truth[u]
    b.to_csv(OUT / "hand_check_b_truth_table.csv", index=False)

    # ---- c) model top-5 and the code's AP@5
    l = lists[u]
    pd.DataFrame({"rank": range(1, 6), "tv_show_id": l, "title": [title.get(p, "") for p in l]}).to_csv(
        OUT / "hand_check_c_model_top5.csv", index=False)
    ap = apk(l, sd.truth[u])
    print(f"c) top-5 {l}; AP@5 (code) = {ap:.6f}")
    return u, c, b, l, ap


if __name__ == "__main__":
    main()
