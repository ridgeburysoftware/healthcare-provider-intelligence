# provider_graph/features.py
from __future__ import annotations

from typing import List, Tuple
import pandas as pd

def topn_per_npi(df: pd.DataFrame, n: int) -> pd.DataFrame:
    df = df.sort_values(["npi", "value"], ascending=[True, False])
    return df.groupby("npi", as_index=False).head(n)

def pivot_dense(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    wide = df.pivot_table(
        index="npi",
        columns="feature_id",
        values="value",
        aggfunc="sum",
        fill_value=0.0,
    )
    wide.columns = wide.columns.astype(str)
    return wide

def standardize_scalars(u: pd.DataFrame, scalar_cols: List[str]) -> pd.DataFrame:
    if u.empty:
        return u
    out = u[["npi"] + [c for c in scalar_cols if c in u.columns]].copy()
    for c in [c for c in scalar_cols if c in out.columns]:
        x = pd.to_numeric(out[c], errors="coerce")
        mu = float(x.mean(skipna=True)) if x.notna().any() else 0.0
        sd = float(x.std(skipna=True)) if x.notna().any() else 1.0
        if sd == 0.0:
            sd = 1.0
        out[f"S:{c}"] = ((x - mu) / sd).fillna(0.0).astype(float)
        out.drop(columns=[c], inplace=True)
    return out

def build_signature_matrix(
    drugs: pd.DataFrame,
    hcpcs: pd.DataFrame,
    unified: pd.DataFrame,
    top_d: int,
    top_b: int,
    include_scalars: bool,
    scalar_cols: List[str],
) -> Tuple[pd.DataFrame, List[str]]:
    # cohort from unified
    cohort = set(unified["npi"].astype(str)) if not unified.empty else set()

    drugs = drugs[drugs["npi"].isin(cohort)]
    hcpcs = hcpcs[hcpcs["npi"].isin(cohort)]

    drugs_top = topn_per_npi(drugs[["npi", "feature_id", "value"]], top_d)
    hcpcs_top = topn_per_npi(hcpcs[["npi", "feature_id", "value"]], top_b)

    D = pivot_dense(drugs_top)
    H = pivot_dense(hcpcs_top)

    if include_scalars and not unified.empty:
        scal = standardize_scalars(unified, scalar_cols).set_index("npi")
    else:
        scal = pd.DataFrame()

    V = D.join(H, how="outer").join(scal, how="left").fillna(0.0)

    # stable ordering
    V = V.loc[V.index.intersection(pd.Index(sorted(cohort)))]
    npis = V.index.astype(str).tolist()
    return V, npis
