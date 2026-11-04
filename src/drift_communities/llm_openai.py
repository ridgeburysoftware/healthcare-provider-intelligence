from __future__ import annotations

import json
import os
from typing import Any, Dict

import streamlit as st


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
