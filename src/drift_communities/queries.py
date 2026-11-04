from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from .neo import run_cypher


@st.cache_data(show_spinner=False, ttl=300)
def list_runs(limit: int = 25) -> pd.DataFrame:
    q = """
    MATCH (c:Community)
    WITH c.run_id AS run_id,
         max(coalesce(c.created_at,0)) AS created_at,
         max(coalesce(c.k,0)) AS k,
         max(coalesce(c.thr,0.0)) AS thr,
         count(c) AS communities
    RETURN run_id, created_at, k, thr, communities
    ORDER BY created_at DESC
    LIMIT $limit
    """
    df = pd.DataFrame(run_cypher(q, limit=int(limit)))
    if not df.empty:
        df["run_id"] = df["run_id"].astype(str)
    return df


@st.cache_data(show_spinner=False, ttl=300)
def community_sizes(run_id: str) -> pd.DataFrame:
    q = """
    MATCH (p:Provider)-[:IN_COMMUNITY {run_id:$run_id}]->(c:Community {run_id:$run_id})
    RETURN c.id AS community_id, count(p) AS n_providers
    ORDER BY community_id
    """
    df = pd.DataFrame(run_cypher(q, run_id=str(run_id)))
    if not df.empty:
        df["community_id"] = df["community_id"].astype(int)
        df["n_providers"] = df["n_providers"].astype(int)
    return df


@st.cache_data(show_spinner=False, ttl=300)
def providers_in_community(run_id: str, cid: int, limit: int = 5000) -> pd.DataFrame:
    q = """
    MATCH (p:Provider)-[r:IN_COMMUNITY {run_id:$run_id}]->(c:Community {run_id:$run_id, id:$cid})
    RETURN
      p.npi AS npi,
      c.id AS community_id,
      toFloat(r.drift_score) AS drift_score,
      coalesce(r.top_peers,'') AS top_peers
    ORDER BY drift_score DESC
    LIMIT $limit
    """
    df = pd.DataFrame(run_cypher(q, run_id=str(run_id), cid=int(cid), limit=int(limit)))
    if not df.empty:
        df["npi"] = df["npi"].astype(str)
        df["community_id"] = df["community_id"].astype(int)
        df["drift_score"] = pd.to_numeric(df["drift_score"], errors="coerce").fillna(0.0)
        df["top_peers"] = df.get("top_peers", "").astype(str)
    return df


@st.cache_data(show_spinner=False, ttl=300)
def bounded_edges(run_id: str, npis: List[str], max_edges: int, min_sim: float) -> pd.DataFrame:
    q = """
    UNWIND $npis AS a
    MATCH (pa:Provider {npi:a})-[r:SIMILAR_TO {run_id:$run_id}]->(pb:Provider)
    WHERE pb.npi IN $npis
      AND r.sim IS NOT NULL
      AND toFloat(r.sim) >= $min_sim
    RETURN pa.npi AS src, pb.npi AS dst, toFloat(r.sim) AS sim
    ORDER BY sim DESC
    LIMIT $max_edges
    """
    df = pd.DataFrame(
        run_cypher(
            q,
            run_id=str(run_id),
            npis=[str(x) for x in npis],
            max_edges=int(max_edges),
            min_sim=float(min_sim),
        )
    )
    if not df.empty:
        df["src"] = df["src"].astype(str)
        df["dst"] = df["dst"].astype(str)
        df["sim"] = pd.to_numeric(df["sim"], errors="coerce").fillna(0.0)
    return df


@st.cache_data(show_spinner=False, ttl=300)
def top_drugs_for_provider(npi: str, k: int = 10) -> pd.DataFrame:
    q = """
    MATCH (p:Provider {npi:$npi})-[r:PRESCRIBES]->(d:Drug)
    RETURN d.id AS id,
           coalesce(d.name, d.id) AS label,
           toFloat(coalesce(r.spend, 0.0)) AS spend,
           toFloat(coalesce(r.count, 0.0)) AS count
    ORDER BY spend DESC, count DESC
    LIMIT $k
    """
    df = pd.DataFrame(run_cypher(q, npi=str(npi), k=int(k)))
    if not df.empty:
        df["id"] = df["id"].astype(str)
        df["label"] = df["label"].astype(str)
        df["spend"] = pd.to_numeric(df["spend"], errors="coerce").fillna(0.0)
        df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(0.0)
    return df


@st.cache_data(show_spinner=False, ttl=300)
def top_hcpcs_for_provider(npi: str, k: int = 10) -> pd.DataFrame:
    q = """
    MATCH (p:Provider {npi:$npi})-[r:BILLS]->(h:HCPCS)
    RETURN h.code AS id,
           'HCPCS ' + h.code AS label,
           toFloat(coalesce(r.spend, 0.0)) AS allowed,
           toFloat(coalesce(r.count, 0.0)) AS count
    ORDER BY allowed DESC, count DESC
    LIMIT $k
    """
    df = pd.DataFrame(run_cypher(q, npi=str(npi), k=int(k)))
    if not df.empty:
        df["id"] = df["id"].astype(str)
        df["label"] = df["label"].astype(str)
        df["allowed"] = pd.to_numeric(df["allowed"], errors="coerce").fillna(0.0)
        df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(0.0)
    return df
