from __future__ import annotations

import os
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from drift_communities.neo import run_cypher
from drift_communities.queries import top_hcpcs_for_provider, top_drugs_for_provider


def _env(name: str, default: str = "") -> str:
    v = os.getenv(name)
    return v if v is not None and v != "" else default


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def _drift_band(d: float) -> str:
    if d < 0.45:
        return "GREEN"
    if d <= 0.65:
        return "YELLOW"
    return "RED"


def evidence_snapshot_metrics(ctx: dict) -> dict:
    """Pure function version of your snapshot (so UI can render it however it wants)."""
    peers = ctx.get("peers") or []
    hcpcs = ctx.get("hcpcs") or []
    drugs = ctx.get("drugs") or []

    peer_sims = [float(p.get("sim") or 0.0) for p in peers]
    sim_avg = sum(peer_sims) / max(1, len(peer_sims)) if peer_sims else 0.0

    def top_delta_sum(items, key, n=3):
        vals = [abs(float(x.get(key) or 0.0)) for x in items]
        vals.sort(reverse=True)
        return sum(vals[:n])

    hc_strength = top_delta_sum(hcpcs, "delta_allowed", 3)
    dr_strength = top_delta_sum(drugs, "delta_spend", 3)

    def top_share(items, key):
        vals = [float(x.get(key) or 0.0) for x in items]
        tot = sum(vals)
        return (max(vals) / tot) if tot > 0 and vals else 0.0

    hc_share = top_share(hcpcs, "allowed")
    dr_share = top_share(drugs, "spend")

    return {
        "peers_used": len(peers),
        "avg_similarity": sim_avg,
        "top_deltas_sum": hc_strength + dr_strength,
        "top_share": max(hc_share, dr_share),
    }


@st.cache_data(show_spinner=False, ttl=900)
def peer_baseline_hcpcs(peer_npis: List[str], hcpcs_codes: List[str]) -> pd.DataFrame:
    if not peer_npis or not hcpcs_codes:
        return pd.DataFrame(columns=["id", "peer_allowed_avg", "peer_count_avg"])

    q = """
    UNWIND $peer_npis AS pnpi
    MATCH (pp:Provider {npi:pnpi})-[r:BILLS]->(h:HCPCS)
    WHERE h.code IN $codes
    RETURN h.code AS id,
           avg(toFloat(coalesce(r.spend,0.0))) AS peer_allowed_avg,
           avg(toFloat(coalesce(r.count,0.0))) AS peer_count_avg
    """
    rows = run_cypher(q, peer_npis=[str(x) for x in peer_npis], codes=[str(c) for c in hcpcs_codes])
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["id", "peer_allowed_avg", "peer_count_avg"])
    df["id"] = df["id"].astype(str)
    df["peer_allowed_avg"] = pd.to_numeric(df["peer_allowed_avg"], errors="coerce").fillna(0.0)
    df["peer_count_avg"] = pd.to_numeric(df["peer_count_avg"], errors="coerce").fillna(0.0)
    return df


@st.cache_data(show_spinner=False, ttl=900)
def peer_baseline_drugs(peer_npis: List[str], drug_ids: List[str]) -> pd.DataFrame:
    if not peer_npis or not drug_ids:
        return pd.DataFrame(columns=["id", "peer_spend_avg", "peer_count_avg"])

    q = """
    UNWIND $peer_npis AS pnpi
    MATCH (pp:Provider {npi:pnpi})-[r:PRESCRIBES]->(d:Drug)
    WHERE d.id IN $ids
    RETURN d.id AS id,
           avg(toFloat(coalesce(r.spend,0.0))) AS peer_spend_avg,
           avg(toFloat(coalesce(r.count,0.0))) AS peer_count_avg
    """
    rows = run_cypher(q, peer_npis=[str(x) for x in peer_npis], ids=[str(i) for i in drug_ids])
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["id", "peer_spend_avg", "peer_count_avg"])
    df["id"] = df["id"].astype(str)
    df["peer_spend_avg"] = pd.to_numeric(df["peer_spend_avg"], errors="coerce").fillna(0.0)
    df["peer_count_avg"] = pd.to_numeric(df["peer_count_avg"], errors="coerce").fillna(0.0)
    return df


@st.cache_data(show_spinner=False, ttl=900)
def build_explain_context(
    run_id: str,
    cid: int,
    npi: str,
    peers_k: int = 5,
    drivers_k: int = 10,
) -> Dict[str, Any]:
    npi = str(npi).strip()
    if not npi:
        return {"error": "Missing npi"}

    # Membership/drift
    q = """
    MATCH (p:Provider {npi:$npi})-[r:IN_COMMUNITY {run_id:$run_id}]->(c:Community {run_id:$run_id, id:$cid})
    RETURN p.npi AS npi, c.id AS community_id, toFloat(r.drift_score) AS drift_score
    LIMIT 1
    """
    rows = run_cypher(q, npi=npi, run_id=str(run_id), cid=int(cid))
    info = rows[0] if rows else None
    if not info:
        return {"error": f"Provider {npi} not found for run_id={run_id} cid={cid}"}

    drift = _safe_float(info.get("drift_score"), 0.0)
    band = _drift_band(drift)

    # Peers
    q = """
    MATCH (p:Provider {npi:$npi})
    CALL {
      WITH p
      MATCH (p)-[r:SIMILAR_TO {run_id:$run_id}]->(q:Provider)
      RETURN q.npi AS peer_npi, toFloat(r.sim) AS sim
      UNION
      WITH p
      MATCH (q:Provider)-[r:SIMILAR_TO {run_id:$run_id}]->(p)
      RETURN q.npi AS peer_npi, toFloat(r.sim) AS sim
    }
    RETURN peer_npi, sim
    ORDER BY sim DESC
    LIMIT $k
    """
    rows = run_cypher(q, npi=npi, run_id=str(run_id), k=int(max(5, peers_k)))
    peers_df = pd.DataFrame(rows)

    if peers_df.empty:
        peer_npis: List[str] = []
        peers_payload: List[Dict[str, Any]] = []
    else:
        peers_df["peer_npi"] = peers_df["peer_npi"].astype(str)
        peers_df["sim"] = pd.to_numeric(peers_df["sim"], errors="coerce").fillna(0.0)
        peers_df = peers_df.sort_values("sim", ascending=False).head(int(peers_k))
        peer_npis = peers_df["peer_npi"].tolist()
        peers_payload = peers_df.to_dict(orient="records")

    # Provider drivers
    hcpcs_df = top_hcpcs_for_provider(npi, k=int(drivers_k))
    drugs_df = top_drugs_for_provider(npi, k=int(drivers_k))

    hcpcs_codes = hcpcs_df["id"].astype(str).tolist() if not hcpcs_df.empty else []
    drug_ids = drugs_df["id"].astype(str).tolist() if not drugs_df.empty else []

    # Peer baselines
    hcpcs_base = peer_baseline_hcpcs(peer_npis, hcpcs_codes)
    drugs_base = peer_baseline_drugs(peer_npis, drug_ids)

    # Merge + deltas
    if not hcpcs_df.empty:
        hc = hcpcs_df.merge(hcpcs_base, on="id", how="left").fillna({"peer_allowed_avg": 0.0, "peer_count_avg": 0.0})
        hc["delta_allowed"] = hc["allowed"] - hc["peer_allowed_avg"]
        hc["delta_count"] = hc["count"] - hc["peer_count_avg"]
        hcpcs_payload = hc.to_dict(orient="records")
    else:
        hcpcs_payload = []

    if not drugs_df.empty:
        dr = drugs_df.merge(drugs_base, on="id", how="left").fillna({"peer_spend_avg": 0.0, "peer_count_avg": 0.0})
        dr["delta_spend"] = dr["spend"] - dr["peer_spend_avg"]
        dr["delta_count"] = dr["count"] - dr["peer_count_avg"]
        drugs_payload = dr.to_dict(orient="records")
    else:
        drugs_payload = []

    return {
        "run_id": str(run_id),
        "community_id": int(cid),
        "provider": {"npi": npi, "drift_score": drift, "band": band},
        "peers": peers_payload,
        "hcpcs": hcpcs_payload,
        "drugs": drugs_payload,
        "notes": {
            "peer_baseline_method": "Mean over top similarity peers; baselines computed only for selected provider's top items.",
            "band_thresholds": {"GREEN": "<0.45", "YELLOW": "0.45-0.65", "RED": ">0.65"},
        },
    }
