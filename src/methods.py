"""Method implementations shared by step 4 (and the hybrids): history, ALS, PPR, content. Work on any protocol.Split.

Every scorer returns (items, S) with S = users x items scores over pool items it can score, or ranked lists.
"""
import os

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")  # implicit recommends this; keeps BLAS deterministic

import numpy as np
import pandas as pd
import scipy.sparse as sp
from implicit.als import AlternatingLeastSquares
from implicit.nearest_neighbours import bm25_weight

from protocol import K

SEED = 42


def air_weight(sd, items):
    """log1p(#airings of the programme in the target-window schedule) (DESIGN D28)."""
    return np.log1p(sd.air_t.reindex(items).fillna(0).values)


def rank_lists(sd, users, items, S, positive_only, topn=K):
    """Top-n pool items per row of S (users x items); ties -> global popularity order.
    positive_only: keep only scores > 0, else only finite scores."""
    items = np.asarray(items)
    order = np.argsort(sd.poprank.reindex(items).values, kind="stable")
    items, S = items[order], S[:, order]
    top = np.argsort(-S, axis=1, kind="stable")[:, :topn]
    out = {}
    for r, u in enumerate(users):
        idx = top[r]
        sc = S[r, idx]
        ok = sc > 0 if positive_only else np.isfinite(sc)
        out[u] = items[idx[ok]].tolist()
    return out


def full_ranks(S):
    """Rank (1 = best) of every column within each row, ties by column order."""
    order = np.argsort(-S, axis=1, kind="stable")
    r = np.empty_like(order)
    np.put_along_axis(r, order, np.arange(1, S.shape[1] + 1)[None, :].repeat(S.shape[0], 0), axis=1)
    return r


# ---------------------------------------------------------------- history
def history_scores(sd, variant="count", h=None):
    """User's train-positive programmes that are in the pool, with score. Columns: user_id, tv_show_id, n_pos,
    overlap_s (all train airings), last_week, grank, score."""
    up = sd.up[sd.up.tv_show_id.isin(sd.pool_set)].copy()
    up["grank"] = up.tv_show_id.map(sd.poprank).values
    if variant == "count":
        up["score"] = up.n_pos.astype(float)
    elif variant == "recency":
        pos = sd.pos[sd.pos.tv_show_id.isin(sd.pool_set)]
        age_w = ((sd.train_end - pos.airing_start).dt.total_seconds() / (7 * 86400)).values
        w = pd.Series(0.5 ** (age_w / h)).groupby([pos.user_id.values, pos.tv_show_id.values]).sum()
        up["score"] = w.reindex(pd.MultiIndex.from_arrays([up.user_id.values, up.tv_show_id.values])).values
    elif variant == "expected":
        up["score"] = up.n_pos.values / up.tv_show_id.map(sd.air_tr).values * up.tv_show_id.map(sd.air_t).values
    else:
        raise ValueError(variant)
    return up


def history_lists(sd, variant="count", h=None, topn=K, ties="seconds"):
    """Ranked by score desc -> total train seconds desc -> global popularity (DESIGN D31);
    ties="popularity" skips the seconds key (DESIGN D59)."""
    keys, asc = (["score", "overlap_s", "grank"], [False, False, True]) if ties == "seconds" else (["score", "grank"], [False, True])
    d = history_scores(sd, variant, h).sort_values(["user_id"] + keys, ascending=[True] + asc)
    return {u: g.tolist() for u, g in d.groupby("user_id").head(topn).groupby("user_id").tv_show_id}


# ---------------------------------------------------------------- user x item train matrix
def train_matrix(sd):
    users = np.array(sd.warm)
    items = np.array(sorted(sd.up.tv_show_id.unique()))
    ui = pd.Index(users).get_indexer(sd.up.user_id)
    ii = pd.Index(items).get_indexer(sd.up.tv_show_id)
    R = sp.csr_matrix((sd.up.n_pos.values.astype(np.float32), (ui, ii)), shape=(len(users), len(items)))
    return users, items, R


def confidence(R, conf):
    R = R.copy()
    if conf == "count":
        return R
    if conf == "log1p":
        R.data = np.log1p(R.data)
        return R
    if conf == "bm25":  # implicit's example orientation: items x users in, then transpose back (DESIGN D32)
        return bm25_weight(R.T.tocoo(), K1=100, B=0.8).T.tocsr().astype(np.float32)
    raise ValueError(conf)


def als_scores(sd, users, conf, f, reg, alpha, iterations=15):
    tu, items, R = train_matrix(sd)
    m = AlternatingLeastSquares(factors=f, regularization=reg, alpha=alpha, iterations=iterations,
                                random_state=SEED, use_gpu=False)
    m.fit(confidence(R, conf), show_progress=False)
    rows = pd.Index(tu).get_indexer(users)
    assert (rows >= 0).all(), "ALS scores only for warm users"
    mask = np.isin(items, sd.pool)
    return items[mask], m.user_factors[rows] @ m.item_factors[mask].T


# ---------------------------------------------------------------- personalized PageRank
def transition(B):
    """Row-stochastic transition matrix of the bipartite graph [[0,B],[B^T,0]] and dangling mask."""
    A = sp.bmat([[None, B], [B.T, None]], format="csr", dtype=np.float64)
    deg = np.asarray(A.sum(axis=1)).ravel()
    dangling = deg == 0
    inv = np.where(dangling, 0.0, 1.0 / np.where(dangling, 1.0, deg))
    return (sp.diags(inv) @ A).tocsr(), dangling


def ppr_step(PT, x, E, dangling, alpha):
    """x' = alpha * P^T x + (alpha * dangling mass + (1 - alpha)) * E  (columns = users)."""
    dm = x[dangling].sum(axis=0) if dangling.any() else 0.0
    return alpha * (PT @ x) + (alpha * dm + (1 - alpha)) * E


def ppr(PT, dangling, starts, alpha, tol=1e-6, cap=200):
    n, m = PT.shape[0], len(starts)
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


def ppr_mass_checks(sd):
    tu, items, R = train_matrix(sd)
    P, dangling = transition(R.astype(np.float64))
    PT = P.T.tocsr()
    starts = np.arange(min(len(tu), 500))
    E = np.zeros((PT.shape[0], len(starts)))
    E[starts, np.arange(len(starts))] = 1.0
    x1 = ppr_step(PT, E, E, dangling, 0.85)
    real = np.abs(x1.sum(0) - 1).max()
    B = sp.csr_matrix(np.array([[2.0, 1.0, 0.0], [0.0, 1.0, 0.0]]))
    P2, d2 = transition(B)
    x = np.array([[0.2], [0.1], [0.1], [0.2], [0.4]])  # 0.4 on the dangling item node
    E2 = np.zeros((5, 1))
    E2[0] = 1.0
    syn = ppr_step(P2.T.tocsr(), x, E2, d2, 0.7).sum()
    dropped = (0.7 * (P2.T @ x) + 0.3 * E2).sum()
    return (f"mass check [{sd.name}]: real graph 1 update max|colsum-1|={real:.2e}, dangling nodes={int(dangling.sum())}; "
            f"synthetic dangling graph colsum={syn:.12f} (would be {dropped:.4f} if dangling mass dropped)")


def ppr_scores(sd, users, alpha, chunk=1000):
    tu, items, R = train_matrix(sd)
    nu = len(tu)
    P, dangling = transition(R.astype(np.float64))
    PT = P.T.tocsr()
    starts = pd.Index(tu).get_indexer(users)
    assert (starts >= 0).all(), "PPR scores only for warm users"
    mask = np.isin(items, sd.pool)
    S, its, res = [], [], []
    for c in range(0, len(starts), chunk):
        x, i, r = ppr(PT, dangling, starts[c:c + chunk], alpha)
        S.append(x[nu:][mask].T)
        its.append(i)
        res.append(r)
    its, res = np.concatenate(its), np.concatenate(res)
    conv = {"mean_iter": round(float(its.mean()), 2), "max_iter": int(its.max()),
            "max_residual": float(f"{res.max():.3e}"), "non_converged": int((res >= 1e-6).sum())}
    return items[mask], np.vstack(S), conv


# ---------------------------------------------------------------- content-based tf-idf
def item_tokens(sd):
    sch = pd.concat([sd.train_sched, sd.pool_sched])  # metadata of what airs in train + target windows
    parts = [("cat", sch.tv_show_category), ("gen", sch.tv_show_genre_1), ("gen", sch.tv_show_genre_2),
             ("gen", sch.tv_show_genre_3), ("ch", sch.channel_id.astype(str))]
    toks = []
    for pfx, s in parts:
        v = s.astype(str).str.strip().values
        toks.append(pd.DataFrame({"tv_show_id": sch.tv_show_id.values, "tok": pfx + ":" + v})[v != ""])
    for pfx, col in [("dir", "director"), ("act", "actors")]:
        e = sch[["tv_show_id", col]].drop_duplicates()
        e = e.assign(tok=e[col].str.split(",")).explode("tok")
        e["tok"] = e.tok.str.strip()
        e = e[e.tok.notna() & (e.tok != "")]
        toks.append(pd.DataFrame({"tv_show_id": e.tv_show_id.values, "tok": pfx + ":" + e.tok.values}))
    return pd.concat(toks).drop_duplicates()


def cbf_scores(sd, users):
    tu, items, R = train_matrix(sd)
    tok = item_tokens(sd)
    all_items = np.array(sorted(set(items) | set(sd.pool)))
    tok = tok[tok.tv_show_id.isin(all_items)]
    vocab = pd.Index(sorted(tok.tok.unique()))
    X = sp.csr_matrix((np.ones(len(tok)), (pd.Index(all_items).get_indexer(tok.tv_show_id),
                                           vocab.get_indexer(tok.tok))), shape=(len(all_items), len(vocab)))
    X.data[:] = 1.0  # binary tf
    df = np.asarray((X > 0).sum(axis=0)).ravel()
    X = X @ sp.diags(np.log((1 + X.shape[0]) / (1 + df)) + 1)  # smooth idf
    norms = np.sqrt(np.asarray(X.multiply(X).sum(axis=1)).ravel())
    X = sp.diags(1 / np.where(norms > 0, norms, 1)) @ X
    Xtr = X[pd.Index(all_items).get_indexer(items)]
    Xpool = X[pd.Index(all_items).get_indexer(sd.pool)]
    rows = pd.Index(tu).get_indexer(users)
    assert (rows >= 0).all(), "CBF scores only for warm users"
    Ru = R[rows]
    prof = sp.diags(1 / np.asarray(Ru.sum(axis=1)).ravel()) @ Ru @ Xtr  # positive-count weighted mean
    pn = np.sqrt(np.asarray(prof.multiply(prof).sum(axis=1)).ravel())
    S = (sp.diags(1 / np.where(pn > 0, pn, 1)) @ prof @ Xpool.T).toarray()
    info = (f"items={len(all_items)} vocab={len(vocab)} pool items without tokens="
            f"{int((np.asarray(Xpool.sum(axis=1)).ravel() == 0).sum())}")
    return sd.pool.copy(), S, info
