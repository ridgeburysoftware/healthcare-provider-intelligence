from __future__ import annotations

import streamlit as st
import pandas as pd

from drift_communities.queries import (
    list_runs,
    community_sizes,
    providers_in_community,
    bounded_edges,
)
from drift_communities.graph_viz import build_plotly_graph, drift_band
from drift_communities.explain_context import build_explain_context, evidence_snapshot_metrics
from drift_communities.llm_openai import explain_with_openai
from drift_communities.llm_bedrock import explain_with_bedrock


# -----------------------------
# Snapshot + LLM render helpers
# -----------------------------
def render_evidence_snapshot(ctx: dict) -> None:
    m = evidence_snapshot_metrics(ctx)

    c1, c2, c3, c4 = st.columns(4, gap="large")
    with c1:
        st.caption("Peers used")
        st.metric("", f"{m['peers_used']}")
    with c2:
        st.caption("Avg similarity")
        st.metric("", f"{m['avg_similarity']:.3f}")
    with c3:
        st.caption("Top deltas (HCPCS+Drugs)")
        st.metric("", f"{m['top_deltas_sum']:,.0f}")
    with c4:
        st.caption("Concentration (top share)")
        st.metric("", f"{m['top_share']*100:.1f}%")


def render_compare_bar(provider_val: float, peer_val: float):
    import pandas as pd

    df = pd.DataFrame({
        "label": ["Provider", "Peer Avg"],
        "value": [provider_val, peer_val]
    })

    st.bar_chart(
        df.set_index("label"),
        height=120,
        use_container_width=True
    )

from typing import Any, Dict, List, Optional, Tuple

def _severity_score(
    provider_value: Optional[float],
    peer_avg_value: Optional[float],
    delta: Optional[float],
) -> float:
    """
    Dimensionless severity score: abs(delta) / max(abs(peer_avg), floor)
    Uses peer_avg as baseline so it's comparable across HCPCS vs Drug.
    """
    if delta is None:
        return 0.0

    denom = abs(float(peer_avg_value)) if peer_avg_value is not None else 0.0
    floor = 25.0  # prevents tiny peer avgs from exploding the ratio
    return abs(float(delta)) / max(denom, floor)


def _severity_label(score: float) -> str:
    if score >= 2.0:
        return "HIGH"
    if score >= 0.75:
        return "MED"
    return "LOW"


def _severity_styles(label: str) -> Dict[str, str]:
    label = (label or "LOW").upper()
    if label == "HIGH":
        return {
            "border": "#ef4444",  # red-500
            "bg": "rgba(239,68,68,0.06)",
            "badge_bg": "rgba(239,68,68,0.12)",
            "badge_fg": "#ef4444",
        }
    if label == "MED":
        return {
            "border": "#f59e0b",  # amber-500
            "bg": "rgba(245,158,11,0.07)",
            "badge_bg": "rgba(245,158,11,0.14)",
            "badge_fg": "#b45309",
        }
    return {
        "border": "#22c55e",  # green-500
        "bg": "rgba(34,197,94,0.06)",
        "badge_bg": "rgba(34,197,94,0.12)",
        "badge_fg": "#16a34a",
    }


def _severity_badge_html(label: str, score: float) -> str:
    s = _severity_styles(label)
    return f"""
    <span style="
        display:inline-flex; align-items:center; gap:8px;
        padding:6px 10px; border-radius:999px;
        background:{s['badge_bg']}; color:{s['badge_fg']};
        font-weight:700; font-size:12px;
        border:1px solid rgba(0,0,0,0.05);
        white-space:nowrap;
    ">
      {label} <span style="opacity:.8; font-weight:600;">({score:.2f}×)</span>
    </span>
    """

def render_llm_explanation(out: Dict[str, Any]) -> None:
    summary = (out.get("summary") or "").strip()
    drivers: List[Dict[str, Any]] = out.get("key_drivers") or []
    peer_ctx: Dict[str, Any] = out.get("peer_context") or {}
    caveats: List[str] = out.get("caveats") or []

    # --- Summary ---
    if summary:
        st.success(summary)
    else:
        st.info("No summary returned.")

    st.markdown("### Key drivers")
    if not drivers:
        st.warning("No drivers returned.")
        return

    # OPTIONAL: sort by severity (highest first)
    def _sort_key(d: Dict[str, Any]) -> float:
        ev = d.get("evidence") or {}
        pv = ev.get("provider_value")
        pa = ev.get("peer_avg_value")
        dl = ev.get("delta")
        return _severity_score(pv, pa, dl)

    drivers = sorted(drivers, key=_sort_key, reverse=True)

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

        # Compute severity
        sev_score = _severity_score(pv, pa, dl)
        sev_label = _severity_label(sev_score)
        styles = _severity_styles(sev_label)

        # ---- Styled wrapper, but preserves your internal column layout ----
        st.markdown(
            f"""
            <div style="
              border: 1px solid rgba(148,163,184,0.35);
              border-left: 10px solid {styles['border']};
              background: {styles['bg']};
              border-radius: 16px;
              padding: 14px 14px 6px 14px;
              margin-bottom: 14px;
            ">
            """,
            unsafe_allow_html=True,
        )

        # Top row (Type / Signal / Severity)
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
            st.caption("Severity")
            st.markdown(_severity_badge_html(sev_label, sev_score), unsafe_allow_html=True)

        # Evidence row (Provider / Peer avg / Driver id or Delta)
        e1, e2, e3, e4 = st.columns([1.2, 1.2, 1.2, 1.4], gap="large")
        with e1:
            st.caption("Provider")
            st.metric("", "—" if pv is None else f"{float(pv):,.0f}")
        with e2:
            st.caption("Peer avg")
            st.metric("", "—" if pa is None else f"{float(pa):,.0f}")
        with e3:
            st.caption("Delta vs peers")
            st.metric("", "—" if dl is None else f"{float(dl):,.0f}")
        with e4:
            st.caption("Driver id")
            st.code(_id, language=None)

        # Optional comparison chart (if you already had it)
        if pv is not None and pa is not None:
            st.caption("Provider vs peer comparison")
            try:
                render_compare_bar(float(pv), float(pa))
            except Exception:
                pass

        st.markdown("</div>", unsafe_allow_html=True)

        rows.append(
            {
                "rank": i,
                "severity": sev_label,
                "severity_score": float(sev_score),
                "type": typ,
                "id": _id,
                "label": label,
                "provider": None if pv is None else float(pv),
                "peer_avg": None if pa is None else float(pa),
                "delta": None if dl is None else float(dl),
            }
        )

    # Optional evidence table (same as before, now includes severity)
    st.markdown("#### Evidence table")
    df = pd.DataFrame(rows)
    if not df.empty:
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "rank": st.column_config.NumberColumn("Rank"),
                "severity": st.column_config.TextColumn("Severity"),
                "severity_score": st.column_config.NumberColumn("Score (×)", format="%.2f"),
                "type": st.column_config.TextColumn("Type"),
                "label": st.column_config.TextColumn("Signal"),
                "provider": st.column_config.NumberColumn("Provider", format="%.0f"),
                "peer_avg": st.column_config.NumberColumn("Peer avg", format="%.0f"),
                "delta": st.column_config.NumberColumn("Δ", format="%.0f"),
            },
        )

    # Peer context (unchanged)
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

    # Caveats (optional)
    if caveats:
        with st.expander("Caveats", expanded=False):
            for c in caveats:
                st.write(f"- {c}")

# -----------------------------
# Main app
# -----------------------------
def main() -> None:
    st.set_page_config(
        page_title="Provider Part B/D Utilization Comparison",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown("""
        <style>
        div.stButton > button {
            background-color: #2563eb !important;
            color: white !important;
            border-radius: 10px !important;
            font-weight: 600;
        }
        div.stButton > button:hover {
            background-color: #1d4ed8 !important;
        }
        </style>
        """, unsafe_allow_html=True)
    st.markdown(
        """
        <style>
        /* Force wide mode to actually use the screen */
        .block-container { 
            max-width: 100%;  
            padding-top: 2rem;
            padding-left: 3rem;
            padding-right: 3rem;
        }

        /* Don’t let the app area get “centered narrow” */
        @media (min-width: 1200px) {
            section.main > div { max-width: none !important; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("Provider Part B/D Utilization Comparison")
    st.caption(
        "Graph representation built from provider vectors derived from CMS claims data. "
        "Edges are colored by endpoint drift and darken/thicken with similarity strength (i.e Cosine). "
    )

    runs = list_runs(limit=25)
    if runs.empty:
        st.error("No runs found in Neo4j")
        st.stop()

    run_id = runs.iloc[0]["run_id"]

    with st.sidebar:
        st.markdown("### Peer Group")
        sizes = community_sizes(run_id)
        if sizes.empty:
            st.error("No membership rows for this run_id.")
            st.stop()

        cids = sizes.sort_values("community_id")["community_id"].tolist()
        cid = st.selectbox("group id", cids, index=0)

        st.divider()
        st.markdown("### Controls")
        top20 = st.toggle("Show only top 20 drifted providers", value=False)
        min_sim = st.slider("Min similarity (edges)", 0.0, 0.9, 0.25, 0.05)

        st.divider()
        st.markdown("### Risk Bands")
        st.markdown("- 🟩 green: drift < **0.45**")
        st.markdown("- 🟨 yellow: **0.45–0.65**")
        st.markdown("- 🟥 red: drift > **0.65**")

    members = providers_in_community(run_id, int(cid), limit=5000)
    if members.empty:
        st.info("No providers found for this community.")
        st.stop()

    if top20:
        max_nodes = 20
        max_edges = 450
    else:
        max_nodes = 120
        max_edges = 1200

    nodes_df = members.sort_values("drift_score", ascending=False).head(max_nodes).copy()
    npis = nodes_df["npi"].astype(str).tolist()

    edges = bounded_edges(run_id=run_id, npis=npis, max_edges=max_edges, min_sim=float(min_sim))

    if "dc_selected_npi" not in st.session_state:
        st.session_state["dc_selected_npi"] = ""

    sel = (st.session_state.get("dc_selected_npi") or "").strip() or None
    centroid_id = f"centroid:{run_id}:{cid}"

    fig, _confirmed = build_plotly_graph(
        members=nodes_df[["npi", "drift_score", "top_peers"]],
        edges=edges,
        centroid_id=centroid_id,
        selected_provider=sel,
        expand_drivers=False,
        drugs_k=10,
        hcpcs_k=10,
    )

    st.subheader("Graph View")
    with st.expander("How this graph is constructed", expanded=True):
        st.markdown(
            """
**Provider vectors**  
Each provider is represented as a vector built from practice patterns learned from CMS claims, including:
- Part B service mix (HCPCS frequencies & allowed amounts)
- Part D prescribing patterns (drug mix, volume, spend)
- Utilization intensity and peer-normalized rates

These features are normalized and combined into a single embedding that describes **how a provider practices**.

**Similarity edges (why lines appear)**  
A line is drawn when two providers have **high cosine similarity** between their vectors—meaning their practice patterns are statistically alike.
- **Thicker + darker edge → stronger similarity**
- **No edge → materially different practice profile**

**Drift score (why nodes are colored)**  
Drift measures how far a provider's vector deviates from expected patterns within this community.
- 🟩 Low drift - aligned with peer norms  
- 🟨 Moderate drift - emerging deviation  
- 🟥 High drift - structurally different mix
            """
        )
    st.plotly_chart(fig, use_container_width=True)

    # Quick stats row
    min_d = float(nodes_df["drift_score"].min())
    max_d = float(nodes_df["drift_score"].max())
    c1, c2, c3, c4 = st.columns([1.0, 1.0, 1.5, 1.5], gap="large")
    with c1:
        st.metric("Nodes", f"{len(nodes_df):,}")
    with c2:
        st.metric("Edges", f"{len(edges):,}")
    with c3:
        st.metric("Drift range (shown)", f"{min_d:.3f} → {max_d:.3f}")
    with c4:
        st.metric("Selected", sel if sel else "—")

    st.divider()

    st.subheader("Group Members")
    st.caption("Click the checkbox to select a provider. Sorted by drift_score (descending).")

    members_sorted = (
        members[["npi", "drift_score", "top_peers"]]
        .sort_values("drift_score", ascending=False)
        .copy()
    )
    members_sorted.insert(0, "select", False)

    if sel:
        members_sorted.loc[members_sorted["npi"].astype(str) == sel, "select"] = True

    edited = st.data_editor(
        members_sorted,
        use_container_width=True,
        height=520,
        hide_index=True,
        column_config={
            "select": st.column_config.CheckboxColumn("Select", help="Choose one provider"),
            "npi": st.column_config.TextColumn("NPI"),
            "drift_score": st.column_config.NumberColumn("drift_score", format="%.4f"),
            "top_peers": st.column_config.TextColumn("top_peers"),
        },
        disabled=["npi", "drift_score", "top_peers"],
    )

    picked = edited.loc[edited["select"] == True, "npi"].astype(str).tolist()
    new_sel = picked[-1].strip() if picked else ""

    if new_sel and new_sel != (st.session_state.get("dc_selected_npi") or ""):
        st.session_state["dc_selected_npi"] = new_sel
        st.rerun()

    sel = (st.session_state.get("dc_selected_npi") or "").strip()
    if not sel:
        return

    st.divider()
    st.subheader("Selected Provider Detail")

    row = members[members["npi"].astype(str) == sel]
    if row.empty:
        st.warning("Selected provider is not present in this community.")
        return

    r0 = row.iloc[0]

    a, b, c = st.columns([1.0, 1.2, 2.5], gap="large")
    with a:
        st.metric("NPI", sel)
    with b:
        st.metric("Drift", f"{float(r0['drift_score']):.3f}")
    with c:
        st.metric("Band", drift_band(float(r0["drift_score"])))

    explain_key = f"dc_explain::{run_id}::{int(cid)}::{sel}"
    if "dc_explain_cache" not in st.session_state:
        st.session_state["dc_explain_cache"] = {}

    st.divider()

    h1, h2 = st.columns([3.2, 1.4], gap="large")
    with h1:
        st.subheader("LLM Explanation")
        st.caption("Explanation using Neo4j data (HCPCS and Drug deltas vs similar peers).")
    with h2:
       # backend = st.selectbox("Backend", ["Bedrock", "OpenAI"], index=0, label_visibility="collapsed")
        backend = "Bedrock"
        explain_clicked = st.button("Explain drift", use_container_width=True)

    if explain_clicked:
        with st.spinner("Generating explanation..."):
            ctx = build_explain_context(
                run_id=str(run_id),
                cid=int(cid),
                npi=str(sel),
                peers_k=5,
                drivers_k=10,
            )
            if backend == "Bedrock":
                out = explain_with_bedrock(ctx)
            else:
                out = explain_with_openai(ctx)

        st.session_state["dc_explain_cache"][explain_key] = {"ctx": ctx, "out": out}
        st.rerun()

    payload = st.session_state["dc_explain_cache"].get(explain_key)
    if not payload:
        st.info("Click **Explain drift** to generate an LLM explanation for the selected provider.")
        return

    ctx = (payload or {}).get("ctx") or {}
    out = (payload or {}).get("out") or {}

    if "error" in out:
        st.error(out["error"])
        if out.get("raw"):
            with st.expander("Raw model output", expanded=False):
                st.code(out["raw"])
        return

    render_evidence_snapshot(ctx)
    st.divider()
    render_llm_explanation(out)


if __name__ == "__main__":
    main()
