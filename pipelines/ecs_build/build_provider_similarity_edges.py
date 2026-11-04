#!/usr/bin/env python3
from __future__ import annotations

import os
import math
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

import pyarrow.dataset as ds
import pyarrow.compute as pc

import faiss
import networkx as nx
import community as community_louvain  # python-louvain

from neo4j import GraphDatabase


# -----------------------------
# Config (ENV)
# -----------------------------
RUN_ID = os.environ.get("RUN_ID", "RUN_2023_01")
YEAR = int(os.environ.get("YEAR", "2023"))

# S3 roots (these should be the dataset roots, not year=... subfolders)
DRUGS_S3 = os.environ["DRUGS_S3"].rstrip("/") + "/"   # .../features/provider_drugs/
HCPCS_S3 = os.environ["HCPCS_S3"].rstrip("/") + "/"   # .../features/provider_hcpcs/
UNIFIED_S3 = os.environ["UNIFIED_S3"].rstrip("/") + "/"  # .../features/provider_unified/

# Signature params (match your local logic defaults)
TOP_D = int(os.environ.get("TOP_D", "25"))
TOP_B = int(os.environ.get("TOP_B", "25"))
TOP_K = int(os.environ.get("TOP_K", "25"))  # FAISS neighbors per provider
SIM_THRESHOLD = float(os.environ.get("SIM_THRESHOLD", "0.35"))
TOP_PEERS = int(os.environ.get("TOP_PEERS", "8"))

# Scalars (optional)
INCLUDE_SCALARS = int(os.environ.get("INCLUDE_SCALARS", "1"))
SCALAR_COLS = [c.strip() for c in os.environ.get(
    "SCALAR_COLS",
    "allowed_per_service,cost_per_claim,combined_outlier_score"
).split(",") if c.strip()]

# Neo4j
NEO4J_URI = os.environ["NEO4J_URI"]         # bolt+s://... or bolt://...
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASS = os.environ["NEO4J_PASS"]
NEO4J_DB   = os.environ.get("NEO4J_DB", "neo4j")

WRITE_BATCH = int(os.environ.get("WRITE_BATCH", "2000"))

RANDOM_STATE = int(os.environ.get("RANDOM_STATE", "42"))


# -----------------------------
# Helpers: read parquet from S3 via PyArrow Dataset
# -----------------------------
def read_long_features(root: str, year: int) -> pd.DataFrame:
    """
    Expects Parquet with columns: npi, year, feature_id, value
    partitioned by year=YYYY (Hive style) OR has a 'year' column.
    """
    dataset = ds.dataset(root, format="parquet")
    cols = ["npi", "year", "feature_id", "value"]

    # Filter year either from column or partition (Arrow handles both)
    table = dataset.to_table(
        columns=cols,
        filter=pc.equal(pc.field("year"), pc.scalar(str(year)))  # year is often string in Athena
    )
    df = table.to_pandas()
    df["npi"] = df["npi"].astype(str)
    df["feature_id"] = df["feature_id"].astype(str)
    df["value"] = pd.to_numeric(df["value"], errors="coerce").fillna(0.0).astype(float)

    # Keep only 10-digit NPIs
    df = df[df["npi"].str.len() == 10].copy()
    return df


def read_unified(root: str, year: int, scalar_cols: List[str]) -> pd.DataFrame:
    dataset = ds.dataset(root, format="parquet")

    base_cols = ["npi", "year"]
    cols = base_cols + scalar_cols
    # some cols might not exist; read what exists
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


def standardize_scalars(u: pd.DataFrame, scalar_cols: List[str]) -> pd.DataFrame:
    """Z-score per scalar column and rename to S:<col>."""
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


# -----------------------------
# Build dense signature vectors like your local code
# -----------------------------
def topn_per_npi(df: pd.DataFrame, n: int) -> pd.DataFrame:
    # df has npi, feature_id, value
    df = df.sort_values(["npi", "value"], ascending=[True, False])
    return df.groupby("npi", as_index=False).head(n)


def pivot_dense(df: pd.DataFrame) -> pd.DataFrame:
    # Wide: index=npi, columns=feature_id, values=value
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


def build_signature_matrix() -> Tuple[pd.DataFrame, List[str]]:
    drugs = read_long_features(DRUGS_S3, YEAR)
    hcpcs = read_long_features(HCPCS_S3, YEAR)

    # cohort from unified (this is what your local code effectively does)
    unified = read_unified(UNIFIED_S3, YEAR, SCALAR_COLS)
    cohort = set(unified["npi"].astype(str))

    drugs = drugs[drugs["npi"].isin(cohort)]
    hcpcs = hcpcs[hcpcs["npi"].isin(cohort)]

    drugs_top = topn_per_npi(drugs[["npi", "feature_id", "value"]], TOP_D)
    hcpcs_top = topn_per_npi(hcpcs[["npi", "feature_id", "value"]], TOP_B)

    D = pivot_dense(drugs_top)
    H = pivot_dense(hcpcs_top)

    # scalars
    if INCLUDE_SCALARS and not unified.empty:
        scal = standardize_scalars(unified, SCALAR_COLS)
        scal = scal.set_index("npi")
    else:
        scal = pd.DataFrame()

    # join & fill
    V = D.join(H, how="outer").join(scal, how="left").fillna(0.0)

    # keep only cohort ordering
    V = V.loc[V.index.intersection(pd.Index(sorted(cohort)))]
    npis = V.index.astype(str).tolist()
    return V, npis


# -----------------------------
# FAISS + Louvain + drift
# -----------------------------
def compute_similarity_and_communities(V: pd.DataFrame, npis: List[str]):
    X = np.ascontiguousarray(V.values, dtype=np.float32)
    faiss.normalize_L2(X)

    n, d = X.shape
    index = faiss.IndexFlatIP(d)
    index.add(X)

    sims, idxs = index.search(X, TOP_K + 1)

    G = nx.Graph()
    G.add_nodes_from(range(n))

    # for top_peers text (same idea as your code)
    neighbors: Dict[str, List[Tuple[str, float]]] = {npis[i]: [] for i in range(n)}
    edges: List[Tuple[int, int, float]] = []

    for i in range(n):
        for r in range(1, TOP_K + 1):
            j = int(idxs[i, r])
            s = float(sims[i, r])
            if j == i or s < SIM_THRESHOLD:
                continue
            # undirected graph edge for Louvain
            G.add_edge(i, j, weight=s)
            # directed-ish storage for Neo edges (we’ll write both directions)
            edges.append((i, j, s))

            if len(neighbors[npis[i]]) < TOP_PEERS:
                neighbors[npis[i]].append((npis[j], s))

    part = community_louvain.best_partition(G, weight="weight", random_state=RANDOM_STATE)

    comm_to_ids: Dict[int, List[int]] = {}
    for i, cid in part.items():
        comm_to_ids.setdefault(cid, []).append(i)

    centroids: Dict[int, np.ndarray] = {}
    for cid, ids in comm_to_ids.items():
        c = X[ids].mean(axis=0)
        norm = float(np.linalg.norm(c))
        if norm > 0:
            c = c / norm
        centroids[cid] = c

    drift_score = np.zeros(n, dtype=np.float32)
    for i in range(n):
        cid = int(part.get(i, -1))
        c = centroids.get(cid)
        if c is None:
            drift_score[i] = 1.0
        else:
            drift_score[i] = 1.0 - float(np.dot(X[i], c))

    # package provider rows
    provider_rows = []
    for i in range(n):
        npi = npis[i]
        cid = int(part.get(i, -1))
        top_peers = ", ".join([p for p, _ in neighbors[npi]])
        provider_rows.append((npi, cid, float(drift_score[i]), top_peers))

    return edges, provider_rows, part


# -----------------------------
# Neo4j writes (batched)
# -----------------------------
def neo_write(driver, cypher: str, rows: List[dict], batch_size: int = 2000):
    with driver.session(database=NEO4J_DB) as sess:
        for i in range(0, len(rows), batch_size):
            chunk = rows[i:i + batch_size]
            sess.run(cypher, rows=chunk)


def main():
    print(f"RUN_ID={RUN_ID} YEAR={YEAR}")
    V, npis = build_signature_matrix()
    print(f"Signature matrix: providers={len(npis)} dims={V.shape[1]}")

    edges, provider_rows, part = compute_similarity_and_communities(V, npis)
    print(f"Similarity edges (pre-write): {len(edges)} (directed pairs)")

    # Convert to Neo batches
    # 1) Ensure Provider nodes exist (match your current model: Provider{npi})
    providers_payload = [{"npi": npi} for npi in npis]

    # 2) Community nodes (Community{run_id, id})
    comm_ids = sorted(set(int(cid) for cid in part.values()))
    comm_payload = [{"run_id": RUN_ID, "id": int(cid), "created_at": int(pd.Timestamp.utcnow().timestamp())} for cid in comm_ids]

    # 3) IN_COMMUNITY relationships
    incomm_payload = []
    for (npi, cid, drift, top_peers) in provider_rows:
        incomm_payload.append({
            "run_id": RUN_ID,
            "npi": npi,
            "cid": int(cid),
            "drift_score": float(drift),
            "top_peers": top_peers,
        })

    # 4) SIMILAR_TO relationships (write both directions for UI convenience)
    sim_payload = []
    for (i, j, s) in edges:
        a = npis[i]
        b = npis[j]
        sim_payload.append({"run_id": RUN_ID, "a": a, "b": b, "sim": float(s)})
        sim_payload.append({"run_id": RUN_ID, "a": b, "b": a, "sim": float(s)})

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))

    # Create providers if missing
    neo_write(
        driver,
        """
        UNWIND $rows AS r
        MERGE (:Provider {npi:r.npi})
        """,
        providers_payload,
        batch_size=WRITE_BATCH,
    )

    # Create community nodes
    neo_write(
        driver,
        """
        UNWIND $rows AS r
        MERGE (c:Community {run_id:r.run_id, id:r.id})
        ON CREATE SET c.created_at = r.created_at
        """,
        comm_payload,
        batch_size=WRITE_BATCH,
    )

    # Clear existing relationships for this run_id (optional but usually correct)
    with driver.session(database=NEO4J_DB) as sess:
        sess.run("MATCH ()-[r:SIMILAR_TO {run_id:$run_id}]->() DELETE r", run_id=RUN_ID)
        sess.run("MATCH (:Provider)-[r:IN_COMMUNITY {run_id:$run_id}]->(:Community {run_id:$run_id}) DELETE r", run_id=RUN_ID)

    # Write SIMILAR_TO
    neo_write(
        driver,
        """
        UNWIND $rows AS r
        MATCH (a:Provider {npi:r.a})
        MATCH (b:Provider {npi:r.b})
        MERGE (a)-[rel:SIMILAR_TO {run_id:r.run_id}]->(b)
        SET rel.sim = r.sim
        """,
        sim_payload,
        batch_size=WRITE_BATCH,
    )

    # Write IN_COMMUNITY
    neo_write(
        driver,
        """
        UNWIND $rows AS r
        MATCH (p:Provider {npi:r.npi})
        MATCH (c:Community {run_id:r.run_id, id:r.cid})
        MERGE (p)-[rel:IN_COMMUNITY {run_id:r.run_id}]->(c)
        SET rel.drift_score = r.drift_score,
            rel.top_peers   = r.top_peers
        """,
        incomm_payload,
        batch_size=WRITE_BATCH,
    )

    driver.close()

    print("✅ Done. Wrote Providers, Communities, SIMILAR_TO, IN_COMMUNITY.")


if __name__ == "__main__":
    main()
