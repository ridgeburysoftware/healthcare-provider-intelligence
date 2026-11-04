from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from drift_communities.queries import (

    top_hcpcs_for_provider,
    top_drugs_for_provider,
)
from drift_communities.neo import run_cypher  


# -----------------------------
# Helpers
# -----------------------------
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

def render_evidence_snapshot(ctx: dict) -> None:
    peers = ctx.get("peers") or []
    hcpcs = ctx.get("hcpcs") or []
    drugs = ctx.get("drugs") or []

    peer_sims = [float(p.get("sim") or 0.0) for p in peers]
    sim_avg = sum(peer_sims) / max(1, len(peer_sims)) if peer_sims else 0.0

    # “strength” = sum of top 3 absolute deltas
    def top_delta_sum(items, key, n=3):
        vals = [abs(float(x.get(key) or 0.0)) for x in items]
        vals.sort(reverse=True)
        return sum(vals[:n])

    hc_strength = top_delta_sum(hcpcs, "delta_allowed", 3)
    dr_strength = top_delta_sum(drugs, "delta_spend", 3)

    # concentration = top item share of total (simple “is this spiky?”)
    def top_share(items, key):
        vals = [float(x.get(key) or 0.0) for x in items]
        tot = sum(vals)
        return (max(vals) / tot) if tot > 0 and vals else 0.0

    hc_share = top_share(hcpcs, "allowed")
    dr_share = top_share(drugs, "spend")

    c1, c2, c3, c4 = st.columns(4, gap="large")
    with c1:
        st.caption("Peers used")
        st.metric("", f"{len(peers)}")
    with c2:
        st.caption("Avg similarity")
        st.metric("", f"{sim_avg:.3f}")
    with c3:
        st.caption("Top deltas (HCPCS+Drugs)")
        st.metric("", f"{(hc_strength + dr_strength):,.0f}")
    with c4:
        st.caption("Concentration (top share)")
        st.metric("", f"{max(hc_share, dr_share)*100:.1f}%")


# -----------------------------
# Neo4j peer baselines (bounded)
# -----------------------------
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


# -----------------------------
# Context builder
# -----------------------------
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

    # Membership/drift (use your query if it exists; else re-query directly)
    info = None
    try:
        info = provider_membership(run_id, npi)  # type: ignore
    except Exception:
        info = None

    if not info:
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

    # Peers (top similarity)
    try:
        peers_df = top_similar_peers_from_edges(run_id, npi, k=int(max(5, peers_k)))  # type: ignore
    except Exception:
        # fallback cypher if your queries.py doesn't export that function
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

    if peers_df is None or peers_df.empty:
        peer_npis: List[str] = []
        peers_payload: List[Dict[str, Any]] = []
    else:
        peers_df = peers_df.copy()
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

    # Peer baselines (only for same codes/ids)
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
        "provider": {
            "npi": npi,
            "drift_score": drift,
            "band": band,
        },
        "peers": peers_payload,
        "hcpcs": hcpcs_payload,
        "drugs": drugs_payload,
        "notes": {
            "peer_baseline_method": "Mean over top similarity peers; baselines computed only for selected provider's top items.",
            "band_thresholds": {"GREEN": "<0.45", "YELLOW": "0.45-0.65", "RED": ">0.65"},
        },
    }


# -----------------------------
# OpenAI call
# -----------------------------
@st.cache_data(show_spinner=False, ttl=1800)
@st.cache_data(show_spinner=False, ttl=1800)
def explain_with_openai(context: Dict[str, Any]) -> Dict[str, Any]:
    if "error" in context:
        return {"error": context["error"]}

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {"error": "Missing OPENAI_API_KEY in environment."}

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

    from openai import OpenAI  # type: ignore

    client = OpenAI(api_key=api_key)

    system = (
        "You are a healthcare claims analytics explainer. "
        "Explain the provider's drift score using ONLY the evidence provided (HCPCS/Drug deltas vs peers, peer sims). "
        "Do not speculate beyond the data. If evidence is insufficient, say so. "
        "Return STRICT JSON only."
    )

    user = {
        "task": "Explain why this provider has its drift score in this community.",
        "context": context,
        "output_schema": {
            "summary": "string (1-2 sentences)",
            "key_drivers": [
                {
                    "type": "HCPCS|Drug|Utilization|Other",
                    "id": "string",
                    "label": "string",
                    "why_it_matters": "string",
                    "evidence": {
                        "provider_value": "number",
                        "peer_avg_value": "number",
                        "delta": "number",
                    },
                }
            ],
            "peer_context": {"peers_used": ["string"], "interpretation": "string"},
            "caveats": ["string"],
        },
        "rules": [
            "Prefer the largest positive deltas (provider >> peer avg) as drivers.",
            "Cite concrete numbers in evidence fields.",
            "If there are no peers or no driver rows, state what is missing.",
        ],
    }

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user)},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )

    text = resp.choices[0].message.content or "{}"
    try:
        return json.loads(text)
    except Exception:
        return {"error": "Model did not return valid JSON.", "raw": text}




def render_llm_explanation(out: Dict[str, Any]) -> None:
    """
    Renders the structured JSON explanation into a clean UI.
    Expected keys:
      - summary: str
      - key_drivers: list[dict]
      - peer_context: dict (optional)
      - caveats: list[str] (optional)
    """
    summary = (out.get("summary") or "").strip()
    drivers: List[Dict[str, Any]] = out.get("key_drivers") or []
    peer_ctx: Dict[str, Any] = out.get("peer_context") or {}
    caveats: List[str] = out.get("caveats") or []

    # --- Summary (nice callout) ---
    if summary:
        st.success(summary)
    else:
        st.info("No summary returned.")

    # --- Drivers as cards + evidence table ---
    st.markdown("### Key drivers")
    if not drivers:
        st.warning("No drivers returned.")
    else:
        rows = []
        for i, d in enumerate(drivers, start=1):
            typ = str(d.get("type") or "—")
            _id = str(d.get("id") or "—")
            label = str(d.get("label") or _id)
            why = str(d.get("why_it_matters") or "").strip()

            ev = d.get("evidence") or {}
            pv = ev.get("provider_value")
            pa = ev.get("peer_avg_value")
            dl = ev.get("delta")

            # Card-style layout
            with st.container(border=True):
                top = st.columns([1.1, 2.4, 1.1], gap="large")
                with top[0]:
                    st.caption("Type")
                    st.markdown(f"**{typ}**")
                with top[1]:
                    st.caption("Signal")
                    st.markdown(f"**{label}**")
                    if why:
                        st.write(why)
                with top[2]:
                    st.caption("Delta vs peers")
                    if dl is None:
                        st.markdown("—")
                    else:
                        st.markdown(f"**{float(dl):,.0f}**")

                # Evidence row
                e1, e2, e3 = st.columns(3, gap="large")
                with e1:
                    st.caption("Provider")
                    st.metric("", "—" if pv is None else f"{float(pv):,.0f}")
                with e2:
                    st.caption("Peer avg")
                    st.metric("", "—" if pa is None else f"{float(pa):,.0f}")
                with e3:
                    st.caption("Driver id")
                    st.code(_id, language=None)

            # Build table rows
            rows.append(
                {
                    "rank": i,
                    "type": typ,
                    "id": _id,
                    "label": label,
                    "provider": None if pv is None else float(pv),
                    "peer_avg": None if pa is None else float(pa),
                    "delta": None if dl is None else float(dl),
                }
            )

        st.markdown("#### Evidence table")
        df = pd.DataFrame(rows)
        if not df.empty:
            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "rank": st.column_config.NumberColumn("Rank"),
                    "type": st.column_config.TextColumn("Type"),
                    "label": st.column_config.TextColumn("Signal"),
                    "provider": st.column_config.NumberColumn("Provider", format="%.0f"),
                    "peer_avg": st.column_config.NumberColumn("Peer avg", format="%.0f"),
                    "delta": st.column_config.NumberColumn("Δ", format="%.0f"),
                },
            )

    # --- Peer context ---
    peers_used = peer_ctx.get("peers_used") or []
    interp = (peer_ctx.get("interpretation") or "").strip()
    with st.expander("Peer context", expanded=False):
        if peers_used:
            st.caption("Peers used")
            st.write(", ".join([str(x) for x in peers_used]))
        if interp:
            st.caption("Interpretation")
            st.write(interp)
        if not peers_used and not interp:
            st.write("No peer context returned.")

   
