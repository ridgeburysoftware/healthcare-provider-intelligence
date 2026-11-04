# provider_graph/io_arrow.py
from __future__ import annotations

from typing import List
import pandas as pd
import pyarrow.dataset as ds
import pyarrow.compute as pc

def read_long_features(root: str, year: int) -> pd.DataFrame:
    dataset = ds.dataset(root, format="parquet")
    cols = ["npi", "year", "feature_id", "value"]

    table = dataset.to_table(
        columns=cols,
        filter=pc.equal(pc.field("year"), pc.scalar(str(year)))
    )
    df = table.to_pandas()
    df["npi"] = df["npi"].astype(str)
    df["feature_id"] = df["feature_id"].astype(str)
    df["value"] = pd.to_numeric(df["value"], errors="coerce").fillna(0.0).astype(float)
    df = df[df["npi"].str.len() == 10].copy()
    return df

def read_unified(root: str, year: int, scalar_cols: List[str]) -> pd.DataFrame:
    dataset = ds.dataset(root, format="parquet")
    base_cols = ["npi", "year"]
    cols = base_cols + scalar_cols

    schema_names = set(dataset.schema.names)
    cols = [c for c in cols if c in schema_names]

    table = dataset.to_table(
        columns=cols,
        filter=pc.equal(pc.field("year"), pc.scalar(str(year)))
    )
    df = table.to_pandas()
    df["npi"] = df["npi"].astype(str)
    df = df[df["npi"].str.len() == 10].copy()
    return df
