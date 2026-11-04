from __future__ import annotations

from typing import Optional

import streamlit as st
import plotly.graph_objects as go


def plotly_click_value(fig: go.Figure) -> Optional[str]:
    """
    Returns clicked provider NPI if streamlit-plotly-events is installed.
    Otherwise just renders fig and returns None.
    """
    try:
        from streamlit_plotly_events import plotly_events  # type: ignore
    except Exception:
        st.plotly_chart(fig, use_container_width=True)
        return None

    selected = plotly_events(fig, click_event=True, hover_event=False, select_event=False, override_height=560)
    if not selected:
        return None

    p0 = selected[0]
    cd = p0.get("customdata")
    # provider customdata = (npi, drift, band)
    if isinstance(cd, (list, tuple)) and len(cd) >= 1:
        npi = str(cd[0])
        if npi and npi != "centroid":
            return npi
    return None
