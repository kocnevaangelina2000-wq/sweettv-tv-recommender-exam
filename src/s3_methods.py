"""Step 3: methods/components evaluated alone on validation (train 11-20 -> truth 21-30).

Same cohort, pool, shared fallback (protocol.channel_fallback) and MAP@5 for every row.
Run: .venv/bin/python src/s3_methods.py   (writes logs/s3_grid.csv; prints the summary table)
"""
import os

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")  # implicit recommends this; also keeps BLAS deterministic

import itertools
import time

import numpy as np
import pandas as pd
import scipy.sparse as sp
from implicit.als import AlternatingLeastSquares

from load import ROOT, load_sched, load_sub
from protocol import (K, SPLITS, THR, channel_fallback, check_lists, fill, ground_truth, load_interactions, mapk,
                      pool_programmes, popularity)

SEED = 42
TRAIN_END = pd.Timestamp("2020-05-18 00:00:00")  # start of ISO week 21 = end of validation train period


class Ctx:
    """Everything shared by all methods on the validation split."""

    def __init__(self):
        spl = SPLITS["val"]
        inter = load_interactions()
        self.tr = inter[inter.period.isin(spl["train"])]
        self.truth = ground_truth(inter[inter.period == spl["target"]])
        self.cohort = sorted(self.truth)
        test = set(load_sub().user_id)
        self.cohort_test = [u for u in self.cohort if u in test]
        self.pool_sched = pool_programmes(spl["target"])
        self.pool = np.array(sorted(set(self.pool_sched.tv_show_id)))
        self.pool_set = set(self.pool.tolist())
        self.air_t = self.pool_sched.groupby("tv_show_id").size()  # airings in target schedule
        trs = pd.concat([load_sched(p) for p in spl["train"]])
        self.air_tr = trs[trs.tv_show_id != 0].groupby("tv_show_id").size()  # airings in train schedule
        self.pop = popularity(self.tr, self.pool_set)
        self.poprank = pd.Series(np.arange(len(self.pop)), index=self.pop.tv_show_id.values)
        t = time.perf_counter()
        self.fb = channel_fallback(self.cohort, self.tr, spl["train"], self.pool_sched, self.pop)
        self.fb_time = time.perf_counter() - t
        self.pos = self.tr[self.tr.screen_time >= THR]
        self.up = (self.pos.groupby(["user_id", "tv_show_id"])
                   .agg(n_pos=("airing_id", "size"), overlap_s=("overlap_s", "sum")).reset_index())
        self.hist = {u: set(g) for u, g in self.up.groupby("user_id").tv_show_id}
        self.cohort_warm = [u for u in self.cohort if u in self.hist]
        print(f"cohort={len(self.cohort)} test-subset={len(self.cohort_test)} warm (train positives)="
              f"{len(self.cohort_warm)} cold={len(self.cohort) - len(self.cohort_warm)} pool={len(self.pool)} "
              f"train positives={len(self.pos)} train (user,programme) pairs={len(self.up)} "
              f"shared fallback for cohort built in {self.fb_time:.2f}s")

    def finish(self, partial):
        """Method list (may be short / missing) + remaining slots from the user's shared fallback list."""
        return {u: fill(partial.get(u, []), self.fb[u]) for u in self.cohort}

    def rank_matrix(self, users, items, S, positive_only):
        """Top-K pool items per row of S (users x items); ties -> global popularity order.
        positive_only: keep only scores > 0, else only finite scores."""
        items = np.asarray(items)
        order = np.argsort(self.poprank.reindex(items).values, kind="stable")
        items, S = items[order], S[:, order]
        top = np.argsort(-S, axis=1, kind="stable")[:, :K]
        out = {}
        for r, u in enumerate(users):
            idx = top[r]
            sc = S[r, idx]
            ok = sc > 0 if positive_only else np.isfinite(sc)
            out[u] = items[idx[ok]].tolist()
        return out


ROWS = []


def evaluate(ctx, method, params, partial, runtime, extra=None):
    lists = ctx.finish(partial)
    check_lists(lists, ctx.pool_set)
    m_all = mapk(lists, ctx.truth, ctx.cohort)
    m_test = mapk(lists, ctx.truth, ctx.cohort_test)
    rw = np.mean([len(set(l) & ctx.hist.get(u, set())) / K for u, l in lists.items()])
    row = {"method": method, "params": params, "map5_cohort": m_all, "map5_test": m_test,
           "rewatch_share": rw, "runtime_s": runtime, **(extra or {})}
    ROWS.append(row)
    print(f"  {method:<28} {params:<42} MAP@5 cohort={m_all:.5f} test={m_test:.5f} rewatch={rw:.3f} "
          f"time={runtime:.2f}s" + (f" {extra}" if extra else ""))
    return row


# ---------------------------------------------------------------- popularity (reference, = step 2)
def run_popularity(ctx):
    t = time.perf_counter()
    glob = ctx.pop.tv_show_id.head(K).tolist()
    partial = {u: glob for u in ctx.cohort_warm}
    evaluate(ctx, "popularity (ref)", "global top-5, fallback for cold", partial, time.perf_counter() - t)


# ---------------------------------------------------------------- a) personal history
def run_history(ctx):
    print("== a) personal history")
    up = ctx.up[ctx.up.tv_show_id.isin(ctx.pool_set)].copy()
    up["grank"] = up.tv_show_id.map(ctx.poprank).values
    pos = ctx.pos[ctx.pos.tv_show_id.isin(ctx.pool_set)]
    age_w = ((TRAIN_END - pos.airing_start).dt.total_seconds() / (7 * 86400)).values

    def lists(score):
        t = time.perf_counter()
        d = up.assign(score=score).sort_values(["user_id", "score", "n_pos", "grank"],
                                               ascending=[True, False, False, True])
        top = d.groupby("user_id").head(K)
        return {u: g.tolist() for u, g in top.groupby("user_id").tv_show_id}, time.perf_counter() - t

    t0 = time.perf_counter()
    p, rt = lists(up.n_pos.values.astype(float))
    evaluate(ctx, "history", "score=train positive count", p, time.perf_counter() - t0)
    for h in [2, 4]:
        t0 = time.perf_counter()
        w = pd.Series(0.5 ** (age_w / h)).groupby([pos.user_id.values, pos.tv_show_id.values]).sum()
        sc = w.reindex(pd.MultiIndex.from_arrays([up.user_id.values, up.tv_show_id.values])).values
        p, _ = lists(sc)
        evaluate(ctx, "history", f"recency-weighted count, half-life {h}w", p, time.perf_counter() - t0)
    t0 = time.perf_counter()
    sc = up.n_pos.values / up.tv_show_id.map(ctx.air_tr).values * up.tv_show_id.map(ctx.air_t).values
    p, _ = lists(sc)
    evaluate(ctx, "history", "expected count = pos/airing(train) x airings(target)", p, time.perf_counter() - t0)


# ---------------------------------------------------------------- shared user x item matrix
def train_matrix(ctx):
    users = np.array(sorted(ctx.hist))
    items = np.array(sorted(ctx.up.tv_show_id.unique()))
    ui = pd.Index(users).get_indexer(ctx.up.user_id)
    ii = pd.Index(items).get_indexer(ctx.up.tv_show_id)
    R = sp.csr_matrix((ctx.up.n_pos.values.astype(np.float32), (ui, ii)), shape=(len(users), len(items)))
    return users, items, R


# ---------------------------------------------------------------- b) ALS
def run_als(ctx):
    print("== b) implicit ALS (15 iterations, seed 42)")
    users, items, R = train_matrix(ctx)
    rows = pd.Index(users).get_indexer(ctx.cohort_warm)
    cand_mask = np.isin(items, ctx.pool)
    cand = items[cand_mask]
    airw = np.log1p(ctx.air_t.reindex(cand).values).astype(np.float32)
    print(f"  matrix users={len(users)} items={len(items)} nnz={R.nnz}; train items in pool={cand.size}")
    for conf in ["count", "log1p(count)"]:
        Rc = R.copy()
        if conf != "count":
            Rc.data = np.log1p(Rc.data)
        for f, reg, a in itertools.product([32, 64, 128], [0.01, 0.1], [1, 10, 40]):
            t = time.perf_counter()
            m = AlternatingLeastSquares(factors=f, regularization=reg, alpha=a, iterations=15,
                                        random_state=SEED, use_gpu=False)
            m.fit(Rc, show_progress=False)
            S = m.user_factors[rows] @ m.item_factors[cand_mask].T
            t_fit = time.perf_counter() - t
            params = f"conf={conf} f={f} reg={reg} alpha={a}"
            for var, Sv in [("ALS", S), ("ALS x log1p(airings)", S * airw)]:
                t = time.perf_counter()
                p = ctx.rank_matrix(ctx.cohort_warm, cand, Sv, positive_only=False)
                evaluate(ctx, var, params, p, t_fit + time.perf_counter() - t)


def als_determinism(ctx, f, reg, a, conf):
    users, items, R = train_matrix(ctx)
    if conf != "count":
        R.data = np.log1p(R.data)
    out = []
    for _ in range(2):
        m = AlternatingLeastSquares(factors=f, regularization=reg, alpha=a, iterations=15, random_state=SEED)
        m.fit(R, show_progress=False)
        out.append(m.item_factors.copy())
    print(f"  ALS determinism (two fits, best config): item factors identical={np.array_equal(out[0], out[1])}, "
          f"max abs diff={np.abs(out[0] - out[1]).max():.2e}")


# ---------------------------------------------------------------- c) personalized PageRank
def transition(B):
    """Row-stochastic transition matrix of the bipartite graph [[0,B],[B^T,0]] and dangling mask."""
    nu, ni = B.shape
    A = sp.bmat([[None, B], [B.T, None]], format="csr", dtype=np.float64)
    deg = np.asarray(A.sum(axis=1)).ravel()
    dangling = deg == 0
    inv = np.where(dangling, 0.0, 1.0 / np.where(dangling, 1.0, deg))
    P = sp.diags(inv) @ A
    return P.tocsr(), dangling


def ppr_step(PT, x, E, dangling, alpha):
    """x' = alpha * P^T x + (alpha * dangling mass + (1 - alpha)) * E  (columns = users)."""
    dm = x[dangling].sum(axis=0) if dangling.any() else 0.0
    return alpha * (PT @ x) + (alpha * dm + (1 - alpha)) * E


def ppr(PT, dangling, starts, alpha, tol=1e-6, cap=200):
    n = PT.shape[0]
    m = len(starts)
    E = np.zeros((n, m))
    E[starts, np.arange(m)] = 1.0
    x = E.copy()
    iters = np.full(m, cap)
    resid = np.full(m, np.inf)
    active = np.arange(m)
    for it in range(1, cap + 1):
        xn = ppr_step(PT, x[:, active], E[:, active], dangling, alpha)
        r = np.abs(xn - x[:, active]).sum(axis=0)
        x[:, active] = xn
        resid[active] = r
        done = r < tol
        iters[active[done]] = it
        active = active[~done]
        if active.size == 0:
            break
    return x, iters, resid


def ppr_mass_checks(PT, dangling, nu):
    # real graph, one update from one-hot restarts
    starts = np.arange(min(nu, 500))
    E = np.zeros((PT.shape[0], len(starts)))
    E[starts, np.arange(len(starts))] = 1.0
    x1 = ppr_step(PT, E, E, dangling, 0.85)
    print(f"  mass check (real graph, 500 users, 1 update, alpha=0.85): max |colsum-1|={np.abs(x1.sum(0) - 1).max():.2e}, "
          f"min entry={x1.min():.2e}; dangling nodes in graph={int(dangling.sum())}")
    # synthetic graph with a dangling item (column with no edges) and mass placed on it
    B = sp.csr_matrix(np.array([[2.0, 1.0, 0.0], [0.0, 1.0, 0.0]]))
    P, d = transition(B)
    x = np.array([[0.2], [0.1], [0.1], [0.2], [0.4]])  # 0.4 on the dangling item node 4
    E = np.zeros((5, 1)); E[0] = 1.0
    x1 = ppr_step(P.T.tocsr(), x, E, d, 0.7)
    without = 0.7 * (P.T @ x) + 0.3 * E
    print(f"  mass check (synthetic, dangling node holding 0.4): colsum with dangling return={x1.sum():.12f}, "
          f"colsum if dangling mass were dropped={without.sum():.4f}")


def run_ppr(ctx):
    print("== c) personalized PageRank (alpha = prob. of following an edge; restart 1-alpha at the user)")
    users, items, R = train_matrix(ctx)
    nu = len(users)
    P, dangling = transition(R.astype(np.float64))
    PT = P.T.tocsr()
    ppr_mass_checks(PT, dangling, nu)
    starts = pd.Index(users).get_indexer(ctx.cohort_warm)
    cand_mask = np.isin(items, ctx.pool)
    cand = items[cand_mask]
    airw = np.log1p(ctx.air_t.reindex(cand).values)
    for alpha in [0.3, 0.5, 0.7, 0.85]:
        t = time.perf_counter()
        S, its, res = [], [], []
        for c in range(0, len(starts), 1000):
            x, i, r = ppr(PT, dangling, starts[c:c + 1000], alpha)
            S.append(x[nu:][cand_mask].T)
            its.append(i)
            res.append(r)
        S, its, res = np.vstack(S), np.concatenate(its), np.concatenate(res)
        t_fit = time.perf_counter() - t
        conv = {"mean_iter": round(float(its.mean()), 2), "max_iter": int(its.max()),
                "max_residual": float(f"{res.max():.3e}"), "non_converged": int((res >= 1e-6).sum())}
        for var, Sv in [("PPR", S), ("PPR x log1p(airings)", S * airw)]:
            t = time.perf_counter()
            p = ctx.rank_matrix(ctx.cohort_warm, cand, Sv, positive_only=True)
            evaluate(ctx, var, f"alpha={alpha}", p, t_fit + time.perf_counter() - t, conv)


# ---------------------------------------------------------------- d) content-based
def item_tokens():
    sch = pd.concat([load_sched(p) for p in ["11-20", "21-30"]])  # validation: train + target schedule metadata
    sch = sch[sch.tv_show_id != 0]
    parts = [("cat", sch.tv_show_category), ("gen", sch.tv_show_genre_1), ("gen", sch.tv_show_genre_2),
             ("gen", sch.tv_show_genre_3), ("ch", sch.channel_id.astype(str))]
    toks = [pd.DataFrame({"tv_show_id": sch.tv_show_id.values, "tok": pfx + ":" + s.astype(str).str.strip().values})
            [s.astype(str).str.strip().values != ""] for pfx, s in parts]
    for pfx, col in [("dir", "director"), ("act", "actors")]:
        e = sch[["tv_show_id", col]].drop_duplicates()
        e = e.assign(tok=e[col].str.split(",")).explode("tok")
        e["tok"] = e.tok.str.strip()
        e = e[e.tok.notna() & (e.tok != "")]
        toks.append(pd.DataFrame({"tv_show_id": e.tv_show_id.values, "tok": pfx + ":" + e.tok.values}))
    return pd.concat(toks).drop_duplicates()


def run_content(ctx):
    print("== d) content-based tf-idf (category, genres, channel, director, actors)")
    t = time.perf_counter()
    users, items, R = train_matrix(ctx)
    tok = item_tokens()
    all_items = np.array(sorted(set(items) | set(ctx.pool)))
    tok = tok[tok.tv_show_id.isin(all_items)]
    vocab = pd.Index(sorted(tok.tok.unique()))
    X = sp.csr_matrix((np.ones(len(tok)), (pd.Index(all_items).get_indexer(tok.tv_show_id), vocab.get_indexer(tok.tok))),
                      shape=(len(all_items), len(vocab)))
    X.data[:] = 1.0  # binary tf
    df = np.asarray((X > 0).sum(axis=0)).ravel()
    idf = np.log((1 + X.shape[0]) / (1 + df)) + 1  # smooth idf
    X = X @ sp.diags(idf)
    norms = np.sqrt(np.asarray(X.multiply(X).sum(axis=1)).ravel())
    X = sp.diags(1 / np.where(norms > 0, norms, 1)) @ X
    Xtr = X[pd.Index(all_items).get_indexer(items)]
    Xpool = X[pd.Index(all_items).get_indexer(ctx.pool)]
    rows = pd.Index(users).get_indexer(ctx.cohort_warm)
    Ru = R[rows]
    prof = sp.diags(1 / np.asarray(Ru.sum(axis=1)).ravel()) @ Ru @ Xtr  # positive-count weighted mean
    pn = np.sqrt(np.asarray(prof.multiply(prof).sum(axis=1)).ravel())
    S = (sp.diags(1 / np.where(pn > 0, pn, 1)) @ prof @ Xpool.T).toarray()
    t_fit = time.perf_counter() - t
    print(f"  items={len(all_items)} vocab={len(vocab)} (cat {vocab.str.startswith('cat:').sum()}, gen "
          f"{vocab.str.startswith('gen:').sum()}, ch {vocab.str.startswith('ch:').sum()}, dir "
          f"{vocab.str.startswith('dir:').sum()}, act {vocab.str.startswith('act:').sum()}); "
          f"pool items with no tokens: {int((np.asarray(Xpool.sum(axis=1)).ravel() == 0).sum())}")
    airw = np.log1p(ctx.air_t.reindex(ctx.pool).values)
    for var, Sv in [("content tf-idf", S), ("content tf-idf x log1p(airings)", S * airw)]:
        t = time.perf_counter()
        p = ctx.rank_matrix(ctx.cohort_warm, ctx.pool, Sv, positive_only=True)
        evaluate(ctx, var, "cosine(user profile, item)", p, t_fit + time.perf_counter() - t)


def main():
    ctx = Ctx()
    run_popularity(ctx)
    run_history(ctx)
    run_als(ctx)
    run_ppr(ctx)
    run_content(ctx)
    g = pd.DataFrame(ROWS)
    g.to_csv(ROOT / "logs" / "s3_grid.csv", index=False)
    # selection on validation cohort MAP@5 only; per method variant the best grid point
    best = g.sort_values("map5_cohort", ascending=False).groupby("method", sort=False).head(1)
    best = best.set_index("method").reindex([m for m in g.method.unique() if m in set(best.method)]).reset_index()
    hist_rows = g[g.method == "history"]
    summary = pd.concat([g[g.method == "popularity (ref)"], hist_rows,
                         best[~best.method.isin(["history", "popularity (ref)"])]])
    best_als = g[g.method == "ALS"].sort_values("map5_cohort", ascending=False).iloc[0]
    print(f"best ALS by cohort MAP: {best_als.params}")
    p = dict(kv.split("=") for kv in best_als.params.split(" "))
    als_determinism(ctx, int(p["f"]), float(p["reg"]), float(p["alpha"]), p["conf"])
    print("\n| method | params (selected on validation cohort MAP@5) | MAP@5 cohort | MAP@5 test subset | re-watch share of slots | runtime (s) |")
    print("|---|---|---|---|---|---|")
    for _, r in summary.iterrows():
        print(f"| {r.method} | {r.params} | {r.map5_cohort:.5f} | {r.map5_test:.5f} | {r.rewatch_share:.3f} | {r.runtime_s:.2f} |")


if __name__ == "__main__":
    main()
