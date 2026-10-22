"""Part C item 2: how many truth items are a tv_show_id the user never had in train, but whose exact title
(lowercased, stripped) the user did watch in train - under another labelled id, or on id=0 airtime.
Run: .venv/bin/python src/check_title_transfer.py -> logs/check_title_transfer.log
"""
import pandas as pd

from load import ART
from protocol import Split, load_interactions, load_unlab, window_mask


def norm(s):
    return s.str.lower().str.strip()


def main():
    inter, unlab = load_interactions(), load_unlab()
    air = pd.read_parquet(ART / "airings.parquet", columns=["airing_id", "tv_show_title"])
    title = pd.Series(norm(air.tv_show_title).values, index=air.airing_id.values)
    pairs = pd.read_parquet(ART / "view_airing_pairs.parquet",
                            columns=["user_id", "airing_id", "tv_show_id", "period", "week"])
    for fold in ["A", "B"]:
        sd = Split(fold, inter, unlab)
        tr = sd.tr.assign(title=title.reindex(sd.tr.airing_id.values).values)
        u_ids = tr.groupby("user_id").tv_show_id.agg(set)
        u_titles_lab = tr.groupby("user_id").title.agg(set)
        p0 = pairs[(pairs.tv_show_id == 0) & window_mask(pairs, sd.train_windows)]
        u_titles_0 = p0.assign(title=title.reindex(p0.airing_id.values).values).groupby("user_id").title.agg(set)
        p_titles = sd.pool_sched.assign(t=norm(sd.pool_sched.tv_show_title)).groupby("tv_show_id").t.agg(set)
        n = new = lab = zero = either = 0
        for u, items in sd.truth.items():
            ids = u_ids.get(u, set())
            tl, t0 = u_titles_lab.get(u, set()), u_titles_0.get(u, set())
            for p in items:
                n += 1
                if p in ids:
                    continue
                new += 1
                a, b = bool(p_titles[p] & tl), bool(p_titles[p] & t0)
                lab += a
                zero += b
                either += a or b
        print(f"[{fold}] truth items={n}; id never in user's train={new} ({new / n:.2%}); of all truth items, "
              f"exact title seen in train under another labelled id: {lab} ({lab / n:.2%}); on id=0 airtime: "
              f"{zero} ({zero / n:.2%}); either: {either} ({either / n:.2%})")


if __name__ == "__main__":
    main()
