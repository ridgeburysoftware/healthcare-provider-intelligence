from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import networkx as nx

from .queries import top_drugs_for_provider, top_hcpcs_for_provider

GREEN = "rgba(46, 204, 113, 0.95)"
YELLOW = "rgba(241, 196, 15, 0.95)"
RED = "rgba(231, 76, 60, 0.95)"

EDGE_GREEN = "rgba(46, 204, 113, {a})"
EDGE_YELLOW = "rgba(241, 196, 15, {a})"
EDGE_RED = "rgba(231, 76, 60, {a})"
EDGE_GRAY = "rgba(60, 60, 60, {a})"


def drift_band(d: float) -> str:
    if d < 0.45:
        return "GREEN"
    if d <= 0.65:
        return "YELLOW"
    return "RED"


def band_color(band: str) -> str:
    if band == "GREEN":
        return GREEN
    if band == "YELLOW":
        return YELLOW
    return RED


def edge_color_for_drift(avg_drift: Optional[float], alpha: float) -> str:
    a = max(0.05, min(0.95, float(alpha)))
    if avg_drift is None:
        return EDGE_GRAY.format(a=f"{a:.3f}")
    b = drift_band(float(avg_drift))
    if b == "GREEN":
        return EDGE_GREEN.format(a=f"{a:.3f}")
    if b == "YELLOW":
        return EDGE_YELLOW.format(a=f"{a:.3f}")
    return EDGE_RED.format(a=f"{a:.3f}")


def _scale(v: float, in_min: float, in_max: float, out_min: float, out_max: float) -> float:
    span = (in_max - in_min) if (in_max - in_min) != 0 else 1.0
    t = (v - in_min) / span
    t = max(0.0, min(1.0, t))
    return out_min + (out_max - out_min) * t


@st.cache_data(show_spinner=False, ttl=300)
def layout_with_centroid(npis: List[str], edges: pd.DataFrame, centroid_id: str) -> Dict[str, Tuple[float, float]]:
    """
    Spring layout with fixed centroid at (0,0).
    Ensures all provider nodes exist even if isolated.
    """
    G = nx.Graph()
    providers = [str(n) for n in npis]
    G.add_nodes_from(providers)
    G.add_node(centroid_id)

    if not edges.empty:
        for r in edges.itertuples(index=False):
            a, b = str(r.src), str(r.dst)
            if a == b:
                continue
            if a not in G:
                G.add_node(a)
            if b not in G:
                G.add_node(b)
            G.add_edge(a, b, weight=float(r.sim or 0.0))

    # Connect centroid so layout centers nicely
    for n in providers:
        G.add_edge(centroid_id, n, weight=0.10)

    pos0 = {centroid_id: (0.0, 0.0)}
    pos = nx.spring_layout(
        G,
        seed=42,
        iterations=180,
        pos=pos0,
        fixed=[centroid_id],
        k=None,
    )
    return {str(k): (float(v[0]), float(v[1])) for k, v in pos.items()}


def build_plotly_graph(
    members: pd.DataFrame,
    edges: pd.DataFrame,
    centroid_id: str,
    selected_provider: Optional[str],
    expand_drivers: bool,
    drugs_k: int,
    hcpcs_k: int,
) -> Tuple[go.Figure, Optional[str]]:
    df = members.copy()
    df["npi"] = df["npi"].astype(str)
    df["drift_score"] = pd.to_numeric(df["drift_score"], errors="coerce").fillna(0.0)

    provider_nodes = df["npi"].tolist()
    drift_map: Dict[str, float] = {str(r.npi): float(r.drift_score) for r in df.itertuples(index=False)}

    pos = layout_with_centroid(provider_nodes, edges, centroid_id)

    selected = (selected_provider or "").strip() or None
    if selected and selected not in provider_nodes:
        selected = None

    # Neighbor highlight
    G = nx.Graph()
    if not edges.empty:
        for r in edges.itertuples(index=False):
            a, b = str(r.src), str(r.dst)
            if a == b:
                continue
            G.add_edge(a, b)

    selected_set = set()
    if selected and selected in G:
        selected_set.add(selected)
        selected_set.update(G.neighbors(selected))

    dmin = float(df["drift_score"].min()) if len(df) else 0.0
    dmax = float(df["drift_score"].max()) if len(df) else 1.0
    sizes: List[float] = []
    colors: List[str] = []
    outlines_w: List[int] = []
    outlines_c: List[str] = []

    for npi in provider_nodes:
        d = drift_map.get(npi, 0.0)
        sizes.append(_scale(d, dmin, dmax, 10.0, 26.0))
        colors.append(band_color(drift_band(d)))

        if selected and npi == selected:
            outlines_w.append(4)
            outlines_c.append("black")
        elif selected and npi in selected_set:
            outlines_w.append(2)
            outlines_c.append("black")
        else:
            outlines_w.append(0)
            outlines_c.append("rgba(0,0,0,0)")

    customdata = [(npi, drift_map.get(npi, 0.0), drift_band(drift_map.get(npi, 0.0))) for npi in provider_nodes]
    hover_provider = (
        "Type: Provider<br>"
        "NPI: %{customdata[0]}<br>"
        "Drift: %{customdata[1]:.3f}<br>"
        "Band: %{customdata[2]}<extra></extra>"
    )

    # Edges
    edge_traces: List[go.Scattergl] = []
    if not edges.empty:
        smin = float(edges["sim"].min())
        smax = float(edges["sim"].max())
        for r in edges.itertuples(index=False):
            a, b, sim = str(r.src), str(r.dst), float(r.sim or 0.0)
            if a not in pos or b not in pos:
                continue

            da = drift_map.get(a)
            db = drift_map.get(b)
            avg_d = (float(da) + float(db)) / 2.0 if (da is not None and db is not None) else None

            alpha = _scale(sim, smin, smax, 0.30, 0.95)
            width = _scale(sim, smin, smax, 1.2, 5.0)
            col = edge_color_for_drift(avg_d, alpha)

            x0, y0 = pos[a]
            x1, y1 = pos[b]

            edge_traces.append(
                go.Scattergl(
                    x=[x0, x1],
                    y=[y0, y1],
                    mode="lines",
                    line=dict(width=float(width), color=col),
                    hoverinfo="skip",
                    hovertemplate=None,
                    showlegend=False,
                    name="",
                )
            )

    # Centroid
    cx, cy = pos.get(centroid_id, (0.0, 0.0))
    centroid_trace = go.Scattergl(
        x=[cx],
        y=[cy],
        mode="markers+text",
        text=["Community"],
        textposition="bottom center",
        marker=dict(
            size=34,
            symbol="diamond",
            color="rgba(90,90,90,0.90)",
            line=dict(width=1, color="rgba(0,0,0,0.3)"),
        ),
        hovertemplate="Type: Community centroid<extra></extra>",
        customdata=[("centroid",)],
        showlegend=False,
        name="",
    )

    # Providers
    px = [pos[n][0] for n in provider_nodes]
    py = [pos[n][1] for n in provider_nodes]
    provider_trace = go.Scattergl(
        x=px,
        y=py,
        mode="markers",
        marker=dict(size=sizes, color=colors, line=dict(width=outlines_w, color=outlines_c)),
        hovertemplate=hover_provider,
        customdata=customdata,
        showlegend=False,
        name="",
    )

    # Driver expansion
    driver_traces: List[go.Scattergl] = []
    if expand_drivers and selected:
        ddf = top_drugs_for_provider(selected, k=int(drugs_k))
        hdf = top_hcpcs_for_provider(selected, k=int(hcpcs_k))

        sx, sy = pos.get(selected, (0.0, 0.0))

        driver_nodes: List[Tuple[str, str, str, float, float]] = []
        for rr in ddf.itertuples(index=False):
            driver_nodes.append(("drug:" + str(rr.id), str(rr.label), "Drug", float(rr.spend), float(rr.count)))
        for rr in hdf.itertuples(index=False):
            driver_nodes.append(("hcpcs:" + str(rr.id), str(rr.label), "HCPCS", float(rr.allowed), float(rr.count)))

        if driver_nodes:
            radius = 0.20
            n = len(driver_nodes)
            for idx, (nid, label, typ, amt, cnt) in enumerate(driver_nodes):
                ang = (2.0 * math.pi * idx) / max(1, n)
                pos[nid] = (sx + radius * math.cos(ang), sy + radius * math.sin(ang))

                dsel = drift_map.get(selected, 0.0)
                col = edge_color_for_drift(dsel, 0.65)

                x0, y0 = pos[selected]
                x1, y1 = pos[nid]
                driver_traces.append(
                    go.Scattergl(
                        x=[x0, x1],
                        y=[y0, y1],
                        mode="lines",
                        line=dict(width=2.2, color=col),
                        hovertemplate=f"Type: {typ}<br>{label}<br>Amount={amt:,.0f}<br>Count={cnt:,.0f}<extra></extra>",
                        showlegend=False,
                        name="",
                    )
                )

            dx = [pos[nid][0] for (nid, *_rest) in driver_nodes]
            dy = [pos[nid][1] for (nid, *_rest) in driver_nodes]
            d_custom = [(label, typ, amt, cnt) for (_nid, label, typ, amt, cnt) in driver_nodes]
            d_hover = (
                "Type: %{customdata[1]}<br>"
                "%{customdata[0]}<br>"
                "Amount: %{customdata[2]:,.0f}<br>"
                "Count: %{customdata[3]:,.0f}<extra></extra>"
            )
            driver_traces.append(
                go.Scattergl(
                    x=dx,
                    y=dy,
                    mode="markers",
                    marker=dict(size=14, color="rgba(52, 152, 219, 0.95)", line=dict(width=1, color="rgba(0,0,0,0.15)")),
                    hovertemplate=d_hover,
                    customdata=d_custom,
                    showlegend=False,
                    name="",
                )
            )

    # Clean 3-item legend
    legend_traces = [
        go.Scattergl(x=[None], y=[None], mode="markers", name="Low drift (< 0.45)", marker=dict(size=10, color=GREEN), hoverinfo="skip", showlegend=True),
        go.Scattergl(x=[None], y=[None], mode="markers", name="Medium drift (0.45–0.65)", marker=dict(size=10, color=YELLOW), hoverinfo="skip", showlegend=True),
        go.Scattergl(x=[None], y=[None], mode="markers", name="High drift (> 0.65)", marker=dict(size=10, color=RED), hoverinfo="skip", showlegend=True),
    ]

    fig = go.Figure(data=edge_traces + [centroid_trace, provider_trace] + driver_traces + legend_traces)
    fig.update_layout(
        height=560,
        margin=dict(l=4, r=4, t=12, b=4),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0.0),
        xaxis=dict(visible=False, autorange=True, constrain="domain", rangemode="tozero", scaleanchor="y"),
        yaxis=dict(visible=False, autorange=True, constrain="domain", rangemode="tozero"),
        uirevision="keep",
    )

    return fig, selected
