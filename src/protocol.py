"""Evaluation protocol shared by every method: ground truth, MAP@5, candidate pool, fallback.

Splits (DESIGN D14):
  validation: train periods 11-20, truth from 21-30, pool = labelled programmes in the 21-30 schedule
  final:      train periods 11-20 + 21-30, predict 31-42, pool = labelled programmes in the 31-42 schedule
"""
import numpy as np
import pandas as pd

from load import ART, load_sched

THR = 0.8
K = 5
SPLITS = {
    "val": {"train": ["11-20"], "target": "21-30"},
    "final": {"train": ["11-20", "21-30"], "target": "31-42"},
}


def load_interactions():
    return pd.read_parquet(ART / "interactions.parquet")


def user_programme_stats(inter):
    """Per (user, programme): n_pos = #airings with screen_time >= 0.8, overlap_s = total union seconds
    over all of the user's airings of that programme (DESIGN D15)."""
    g = inter.assign(pos=(inter.screen_time >= THR).astype(np.int64)).groupby(["user_id", "tv_show_id"])
    return g.agg(n_pos=("pos", "sum"), overlap_s=("overlap_s", "sum")).reset_index()


def ground_truth(inter, k=K):
    """Kaggle rule: top-k programmes by #positive airings desc; ties -> total overlap seconds desc
    -> tv_show_id asc. Only programmes with n_pos >= 1. Returns {user_id: [tv_show_id, ...]}."""
    up = user_programme_stats(inter)
    up = up[up.n_pos >= 1].sort_values(["user_id", "n_pos", "overlap_s", "tv_show_id"],
                                       ascending=[True, False, False, True])
    top = up.groupby("user_id").head(k)
    return {u: g.tv_show_id.tolist() for u, g in top.groupby("user_id", sort=False)}


def apk(pred, truth, k=K):
    """AP@k divided by min(k, len(truth)) (Kaggle MAP@k)."""
    if not truth:
        return 0.0
    truth = set(truth)
    hits, s = 0, 0.0
    for i, p in enumerate(pred[:k], 1):
        if p in truth:
            hits += 1
            s += hits / i
    return s / min(k, len(truth))


def mapk(preds, truth, users, k=K):
    """Mean AP over `users`; a user missing from preds scores 0."""
    return float(np.mean([apk(preds.get(u, []), truth[u], k) for u in users]))


def pool_programmes(target):
    s = load_sched(target)
    return s[s.tv_show_id != 0]


def popularity(train_inter, pool_ids):
    """Pool programmes ranked by #positives in train desc, then total train overlap seconds desc, then id asc.
    Pool programmes never seen in train are included at the end (0 positives)."""
    p = (train_inter.assign(pos=(train_inter.screen_time >= THR).astype(np.int64))
         .groupby("tv_show_id").agg(n_pos=("pos", "sum"), overlap_s=("overlap_s", "sum")))
    p = p.reindex(sorted(pool_ids), fill_value=0)
    p.index.name = "tv_show_id"
    return p.reset_index().sort_values(["n_pos", "overlap_s", "tv_show_id"], ascending=[False, False, True])


def user_channel_seconds(train_inter, train_periods):
    """Per (user, channel) watch seconds in train: labelled (union) + unlabelled (id=0) airtime."""
    lab = train_inter.groupby(["user_id", "channel_id"]).overlap_s.sum()
    un = pd.read_parquet(ART / "unlab_seconds.parquet")
    un = un[un.period.isin(train_periods)].groupby(["user_id", "channel_id"]).seconds.sum()
    return lab.add(un, fill_value=0).rename("seconds").reset_index()


def channel_fallback(users, train_inter, train_periods, pool_sched, pop, k=K):
    """Shared fallback (DESIGN D17). score(u, p) = pop_pos(p) * sum of u's train watch-second share over the
    channels where p airs in the target schedule; p with score > 0 ranked desc (ties: global pop order),
    then filled with global pool popularity. Users with no train seconds get global popularity."""
    users = list(users)
    glob = pop.tv_show_id.tolist()
    rank = pd.Series(np.arange(len(pop)), index=pop.tv_show_id)
    pos = pop.set_index("tv_show_id").n_pos
    ucs = user_channel_seconds(train_inter, train_periods)
    ucs = ucs[ucs.user_id.isin(set(users))]
    ucs["share"] = ucs.seconds / ucs.groupby("user_id").seconds.transform("sum")
    pc = pool_sched[["tv_show_id", "channel_id"]].drop_duplicates()
    pc = pc[pc.tv_show_id.map(pos) > 0]
    m = ucs.merge(pc, on="channel_id")
    m = m.groupby(["user_id", "tv_show_id"]).share.sum().reset_index()
    m["score"] = m.share * m.tv_show_id.map(pos).values
    m["grank"] = m.tv_show_id.map(rank).values
    m = m.sort_values(["user_id", "score", "grank"], ascending=[True, False, True])
    top = {u: g.tv_show_id.head(k).tolist() for u, g in m.groupby("user_id", sort=False)}
    return {u: fill(top.get(u, []), glob, k) for u in users}


def fill(lst, glob, k=K):
    """Append items from glob (in order) until the list has k unique ids."""
    out, seen = [], set()
    for x in list(lst) + list(glob):
        if x not in seen:
            out.append(x)
            seen.add(x)
            if len(out) == k:
                break
    return out


def check_lists(preds, pool_ids, k=K):
    pool_ids = set(pool_ids)
    for u, l in preds.items():
        assert len(l) == k and len(set(l)) == k, (u, l)
        assert set(l) <= pool_ids, (u, set(l) - pool_ids)
