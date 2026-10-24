"""Evaluation protocol shared by every method: splits, ground truth, MAP@5, candidate pool, fallback.

A split is declarative: train / target windows are lists of (schedule period, first ISO week, last ISO week)
applied to the airing (source file + ISO week of airing start; DESIGN D6, D29).
  A:     train 11-20 weeks <=15            -> target 11-20 weeks 16-20   (DESIGN D30)
  B:     train 11-20 (whole file)          -> target 21-30               (= step 2/3 validation, "val")
  final: train 11-20 + 21-30               -> target 31-42 (no truth)
  C:     train 11-20 + 21-30 weeks 21-27   -> target 21-30 weeks 28-30   (DESIGN D65; specified after Kaggle scores)
"""
import numpy as np
import pandas as pd

from load import ART, load_sched

THR = 0.8
K = 5
ALL = (0, 99)
SPLITS = {
    "A": {"train": [("11-20", 0, 15)], "target": [("11-20", 16, 20)], "train_end": "2020-04-13"},
    "B": {"train": [("11-20", *ALL)], "target": [("21-30", *ALL)], "train_end": "2020-05-18"},
    "final": {"train": [("11-20", *ALL), ("21-30", *ALL)], "target": [("31-42", *ALL)], "train_end": "2020-07-27"},
    "C": {"train": [("11-20", *ALL), ("21-30", 21, 27)], "target": [("21-30", 28, 30)], "train_end": "2020-07-06"},
}
SPLITS["val"] = SPLITS["B"]


def window_mask(df, windows):
    m = np.zeros(len(df), bool)
    for period, lo, hi in windows:
        m |= (df.period.values == period) & (df.week.values >= lo) & (df.week.values <= hi)
    return m


def load_interactions():
    return pd.read_parquet(ART / "interactions.parquet")


def load_unlab():
    return pd.read_parquet(ART / "unlab_seconds.parquet")


def sched_window(windows, labelled_only=True):
    """Schedule airings in the windows (with ISO week of start)."""
    parts = []
    for period in sorted({w[0] for w in windows}):
        s = load_sched(period)
        s = s.assign(week=s.start_time.dt.isocalendar().week.astype(np.int16).values)
        parts.append(s)
    s = pd.concat(parts, ignore_index=True)
    s = s[window_mask(s, windows)]
    return s[s.tv_show_id != 0] if labelled_only else s


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


def pool_programmes(target_windows):
    if isinstance(target_windows, str):  # backwards compatible: a whole schedule period
        target_windows = [(target_windows, *ALL)]
    return sched_window(target_windows)


def popularity(train_inter, pool_ids):
    """Pool programmes ranked by #positives in train desc, then total train overlap seconds desc, then id asc.
    Pool programmes never seen in train are included at the end (0 positives)."""
    p = (train_inter.assign(pos=(train_inter.screen_time >= THR).astype(np.int64))
         .groupby("tv_show_id").agg(n_pos=("pos", "sum"), overlap_s=("overlap_s", "sum")))
    p = p.reindex(sorted(pool_ids), fill_value=0)
    p.index.name = "tv_show_id"
    return p.reset_index().sort_values(["n_pos", "overlap_s", "tv_show_id"], ascending=[False, False, True])


def user_channel_seconds(train_inter, unlab_train):
    """Per (user, channel) watch seconds in train: labelled (union) + unlabelled (id=0) airtime."""
    lab = train_inter.groupby(["user_id", "channel_id"]).overlap_s.sum()
    un = unlab_train.groupby(["user_id", "channel_id"]).seconds.sum()
    return lab.add(un, fill_value=0).rename("seconds").reset_index()


def channel_share(users, train_inter, unlab_train):
    ucs = user_channel_seconds(train_inter, unlab_train)
    ucs = ucs[ucs.user_id.isin(set(users))].copy()
    ucs["share"] = ucs.seconds / ucs.groupby("user_id").seconds.transform("sum")
    return ucs


def channel_fallback(users, train_inter, unlab_train, pool_sched, pop, k=K):
    """Shared fallback (DESIGN D17). score(u, p) = pop_pos(p) * sum of u's train watch-second share over the
    channels where p airs in the target schedule; p with score > 0 ranked desc (ties: global pop order),
    then filled with global pool popularity. Users with no train seconds get global popularity."""
    users = list(users)
    glob = pop.tv_show_id.tolist()
    rank = pd.Series(np.arange(len(pop)), index=pop.tv_show_id)
    pos = pop.set_index("tv_show_id").n_pos
    ucs = channel_share(users, train_inter, unlab_train)
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


class Split:
    """Everything a method needs for one split."""

    def __init__(self, name, inter=None, unlab=None, eval_users=None):
        spec = SPLITS[name]
        self.name = name
        inter = load_interactions() if inter is None else inter
        unlab = load_unlab() if unlab is None else unlab
        self.train_windows, self.target_windows = spec["train"], spec["target"]
        self.train_end = pd.Timestamp(spec["train_end"])
        self.train_end_week = int(self.train_end.isocalendar()[1])
        self.tr = inter[window_mask(inter, self.train_windows)]
        self.unlab_tr = unlab[window_mask(unlab, self.train_windows)]
        tg = inter[window_mask(inter, self.target_windows)]
        self.truth = ground_truth(tg) if len(tg) else {}
        self.target_up = user_programme_stats(tg) if len(tg) else None
        self.cohort = sorted(self.truth)
        self.pool_sched = sched_window(self.target_windows)
        self.pool = np.array(sorted(set(self.pool_sched.tv_show_id)))
        self.pool_set = set(self.pool.tolist())
        self.air_t = self.pool_sched.groupby("tv_show_id").size()
        self.train_sched = sched_window(self.train_windows)
        self.air_tr = self.train_sched.groupby("tv_show_id").size()
        self.pop = popularity(self.tr, self.pool_set)
        self.poprank = pd.Series(np.arange(len(self.pop)), index=self.pop.tv_show_id.values)
        self.pos = self.tr[self.tr.screen_time >= THR]
        st = user_programme_stats(self.tr)
        last = self.tr.groupby(["user_id", "tv_show_id"]).week.max().rename("last_week").reset_index()
        self.up_all = st.merge(last, on=["user_id", "tv_show_id"])  # all (user, programme) seen in train
        self.up = self.up_all[self.up_all.n_pos >= 1].reset_index(drop=True)  # positives only
        self.hist = {u: set(g) for u, g in self.up.groupby("user_id").tv_show_id}
        self.warm = sorted(self.hist)
        self.eval_users = list(self.cohort if eval_users is None else eval_users)
        self.fb = channel_fallback(self.eval_users, self.tr, self.unlab_tr, self.pool_sched, self.pop)

    def describe(self):
        warm_eval = sum(u in self.hist for u in self.eval_users)
        return (f"[{self.name}] train rows={len(self.tr)} positives={len(self.pos)} warm users={len(self.warm)} "
                f"train programmes(pos)={self.up.tv_show_id.nunique()} | eval users={len(self.eval_users)} "
                f"(warm {warm_eval}, cold {len(self.eval_users) - warm_eval}) | pool={len(self.pool)} "
                f"pool airings={len(self.pool_sched)} | train airings(labelled)={len(self.train_sched)}")

    def finish(self, partial, users=None):
        """Method list (may be short / missing) + remaining slots from the user's shared fallback list."""
        users = self.eval_users if users is None else users
        return {u: fill(partial.get(u, []), self.fb[u]) for u in users}
