"""Raw-file loaders with explicit dtypes/formats, cached to artifacts/*.parquet.

Traps handled here (see BUGLOG.md):
- user_id goes up to 20 digits (> int64 max) -> uint64.
- log timestamps are ISO 'YYYY-MM-DD HH:MM:SS', schedule timestamps are
  'DD.MM.YYYY HH:MM:SS' -> parsed with explicit formats, never inferred.
- log duration column is misspelled 'duraton' -> renamed to 'duration'.
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ART = ROOT / "artifacts"
ART.mkdir(exist_ok=True)

LOG_FILE = "dataset11-30.csv"
SCHED_FILES = {
    "11-20": "export_arh_11-20-final.csv",
    "21-30": "export_arh_21-30-final.csv",
    "31-42": "export_arh_31-42-final.csv",
}
SUB_FILE = "submission.csv"


def _cached(name, build):
    p = ART / f"{name}.parquet"
    if p.exists():
        return pd.read_parquet(p)
    df = build()
    df.to_parquet(p, index=False)
    return df


def load_log():
    def build():
        df = pd.read_csv(DATA / LOG_FILE, dtype=str, keep_default_na=False)
        out = pd.DataFrame({
            "user_id": df["user_id"].astype(np.uint64),
            "vsetv_id": df["vsetv_id"].astype(np.int32),
            "start_time": pd.to_datetime(df["start_time"], format="%Y-%m-%d %H:%M:%S"),
            "stop_time": pd.to_datetime(df["stop_time"], format="%Y-%m-%d %H:%M:%S"),
            "duration": df["duraton"].astype(np.int64),
        })
        return out
    return _cached("log", build)


def load_sched(period):
    def build():
        df = pd.read_csv(DATA / SCHED_FILES[period], dtype=str, keep_default_na=False)
        df["channel_id"] = df["channel_id"].astype(np.int32)
        df["start_time"] = pd.to_datetime(df["start_time"], format="%d.%m.%Y %H:%M:%S")
        df["duration"] = df["duration"].astype(np.int64)
        df["tv_show_id"] = df["tv_show_id"].astype(np.int64)
        df["period"] = period
        return df
    return _cached(f"sched_{period.replace('-', '_')}", build)


def load_sub():
    df = pd.read_csv(DATA / SUB_FILE, dtype=str, keep_default_na=False)
    df["user_id"] = df["user_id"].astype(np.uint64)
    return df
