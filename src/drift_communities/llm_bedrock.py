from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import boto3
import streamlit as st


def _region() -> str:
    return (os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1").strip()


def _looks_like_arn_or_profile(model_id: str) -> bool:
    # accept Bedrock model id OR inference profile ARN
    return (
        model_id.startswith("arn:aws:bedrock:")
        or ":inference-profile/" in model_id
        or model_id.startswith("meta.")
        or model_id.startswith("us.meta.")
    )


def _extract_json_object(text: str) -> Optional[str]:
    # best-effort extraction of first {...} JSON object
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    return m.group(0) if m else None


def _parse_json_with_langchain(text: str) -> Optional[Dict[str, Any]]:
    """
    Optional parser fallback that handles markdown-fenced JSON and minor formatting
    issues more robustly than plain json.loads.
    """
    try:
        from langchain_core.output_parsers import JsonOutputParser  # type: ignore
    except Exception:
        return None

    try:
        parsed = JsonOutputParser().parse(text)
    except Exception:
        return None

    return parsed if isinstance(parsed, dict) else None


def _parse_model_output(text: str) -> Optional[Dict[str, Any]]:
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    parsed = _parse_json_with_langchain(text)
    if parsed is not None:
        return parsed

    extracted = _extract_json_object(text)
    if extracted:
        try:
            parsed = json.loads(extracted)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    return None


def _is_anthropic_model(model_id: str) -> bool:
    return "anthropic" in (model_id or "").lower()


def _extract_text_from_payload(payload: Dict[str, Any]) -> str:
    # Anthropic Messages API shape
    content = payload.get("content")
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                txt = item.get("text")
                if isinstance(txt, str):
                    parts.append(txt)
        if parts:
            return "\n".join(parts).strip()

    # Prompt-style / generic fallbacks
    return str(payload.get("generation") or payload.get("outputText") or payload.get("completion") or "").strip()


def _invoke_text(client, model_id: str, prompt: str, max_gen_len: int, temperature: float, top_p: float):
    if _is_anthropic_model(model_id):
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}],
                }
            ],
            "max_tokens": max_gen_len,
            "temperature": temperature,
            "top_p": top_p,
        }
    else:
        body = {
            "prompt": prompt,
            "max_gen_len": max_gen_len,
            "temperature": temperature,
            "top_p": top_p,
        }
    resp = client.invoke_model(
        modelId=model_id,
        body=json.dumps(body).encode("utf-8"),
        contentType="application/json",
        accept="application/json",
    )
    raw = resp["body"].read().decode("utf-8")
    payload = json.loads(raw)
    text = _extract_text_from_payload(payload)
    return text, payload


def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _severity_bucket(delta: Optional[float], peer_avg: Optional[float]) -> str:
    """
    Language calibration so the model doesn't say "high" when delta is tiny.
    Uses abs(delta)/max(abs(peer_avg), floor) similar to your UI scoring.
    """
    if delta is None:
        return "unknown"
    denom = abs(peer_avg) if peer_avg is not None else 0.0
    floor = 25.0
    score = abs(delta) / max(denom, floor)

    if score >= 2.0:
        return "extreme"
    if score >= 0.75:
        return "material"
    return "small"


def _driver_candidate_rows(context: Dict[str, Any], k: int = 10) -> List[Dict[str, Any]]:
    """
    Create a compact, model-friendly list of candidates with exact evidence numbers.
    We only send what we want the model to talk about.
    """
    out: List[Dict[str, Any]] = []

    # HCPCS
    for r in (context.get("hcpcs") or [])[:k]:
        pid = str(r.get("id") or "")
        label = str(r.get("label") or r.get("id") or pid)
        pv = _safe_float(r.get("allowed"))
        pa = _safe_float(r.get("peer_allowed_avg"))
        dl = _safe_float(r.get("delta_allowed"))
        out.append(
            {
                "type": "HCPCS",
                "id": pid,
                "label": label,
                "evidence": {"provider_value": pv, "peer_avg_value": pa, "delta": dl},
                "severity": _severity_bucket(dl, pa),
            }
        )

    # Drugs
    for r in (context.get("drugs") or [])[:k]:
        pid = str(r.get("id") or "")
        label = str(r.get("label") or r.get("id") or pid)
        pv = _safe_float(r.get("spend"))
        pa = _safe_float(r.get("peer_spend_avg"))
        dl = _safe_float(r.get("delta_spend"))
        out.append(
            {
                "type": "Drug",
                "id": pid,
                "label": label,
                "evidence": {"provider_value": pv, "peer_avg_value": pa, "delta": dl},
                "severity": _severity_bucket(dl, pa),
            }
        )

    # Sort by absolute delta (largest signals first)
    def sort_key(d: Dict[str, Any]) -> float:
        ev = d.get("evidence") or {}
        dl = ev.get("delta")
        return abs(dl) if isinstance(dl, (int, float)) else 0.0

    out.sort(key=sort_key, reverse=True)
    return out


@st.cache_data(show_spinner=False, ttl=1800)
def explain_with_bedrock(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Data-faithful Bedrock explainer for Bedrock models and inference profiles (ARNs).
    Forces the model to only cite provided driver rows and exact numbers.

    Env:
      - BEDROCK_MODEL_ID: inference profile ARN OR a supported model id
      - BEDROCK_MAX_TOKENS (default 700)
      - BEDROCK_TEMPERATURE (default 0.2)
      - BEDROCK_TOP_P (default 0.9)
    """
    if "error" in context:
        return {"error": context["error"]}

    model_id = os.getenv("BEDROCK_MODEL_ID", "").strip()
    if not model_id:
        return {"error": "Missing BEDROCK_MODEL_ID in environment."}
    if not _looks_like_arn_or_profile(model_id):
        return {"error": f"BEDROCK_MODEL_ID doesn't look valid: {model_id}"}

    max_gen_len = int(os.getenv("BEDROCK_MAX_TOKENS", "700"))
    temperature = float(os.getenv("BEDROCK_TEMPERATURE", "0.2"))
    top_p = float(os.getenv("BEDROCK_TOP_P", "0.9"))

    provider = (context.get("provider") or {})
    npi = str((provider.get("npi") or "")).strip()
    drift = provider.get("drift_score")
    band = provider.get("band")

    peers = context.get("peers") or []
    peer_npis = [str(p.get("peer_npi") or p.get("npi") or "") for p in peers][:5]
    peer_sims = [p.get("sim") for p in peers][:5]

    candidates = _driver_candidate_rows(context, k=12)
    candidates = candidates[:10]  # keep prompt small & focused

    # NOTE: We no longer send the entire raw context; we send a compact factual packet.
    # This reduces creative interpretation errors.
    packet = {
        "provider": {"npi": npi, "drift_score": drift, "band": band},
        "peers_used": [{"npi": peer_npis[i], "sim": peer_sims[i]} for i in range(min(len(peer_npis), len(peer_sims)))],
        "driver_candidates": candidates,
    }

    system = (
        "You are a data-faithful healthcare analytics explainer.\n"
        "CRITICAL RULES (must follow):\n"
        "1) Use ONLY the provided driver_candidates. Do not invent codes, drugs, or numbers.\n"
        "2) Every key_driver must copy evidence numbers EXACTLY from driver_candidates (provider_value, peer_avg_value, delta).\n"
        "3) Your language must match magnitude:\n"
        "   - severity='small' => use words like 'slightly'/'modest' and DO NOT say 'high' or 'significant'.\n"
        "   - severity='material' => 'material'/'meaningful deviation'.\n"
        "   - severity='extreme' => 'extreme outlier'/'very large deviation'.\n"
        "4) If delta is near zero (small), you MUST NOT claim it 'drives' drift strongly.\n"
        "5) Output STRICT JSON only. No markdown, no extra keys.\n"
    )

    # We still provide a schema, plus explicit constraints the model must follow.
    output_schema = {
        "summary": "string (1-2 sentences, must be consistent with magnitudes)",
        "key_drivers": [
            {
                "type": "HCPCS|Drug",
                "id": "string (must match a driver_candidates.id)",
                "label": "string (must match driver_candidates.label)",
                "why_it_matters": "string (must reference magnitude correctly)",
                "evidence": {
                    "provider_value": "number",
                    "peer_avg_value": "number",
                    "delta": "number",
                },
                "severity": "LOW|MED|HIGH (derived from candidate.severity)",
            }
        ],
        "peer_context": {"peers_used": ["string"], "interpretation": "string"},
        "caveats": ["string"],
    }

    # Prompt for one-shot analysis.
    prompt = (
        f"{system}\n\n"
        "TASK:\n"
        "Explain why this provider differs from peers using ONLY the factual packet.\n\n"
        "FACTUAL PACKET (JSON):\n"
        f"{json.dumps(packet, ensure_ascii=False)}\n\n"
        "OUTPUT REQUIREMENTS:\n"
        "- Return a JSON object with keys exactly: summary, key_drivers, peer_context, caveats\n"
        "- Choose 2 to 5 key_drivers. Prefer largest absolute deltas, but do NOT overstate small deltas.\n"
        "- Map candidate severity to output severity:\n"
        "    candidate.severity='small'    => severity='LOW'\n"
        "    candidate.severity='material' => severity='MED'\n"
        "    candidate.severity='extreme'  => severity='HIGH'\n"
        "- For each key_driver, copy (type,id,label,evidence) exactly from the matching candidate.\n"
        "- In 'why_it_matters', describe direction: delta>0 means provider > peer avg; delta<0 means provider < peer avg.\n"
        "- If all candidates are 'small', say the evidence is weak/insufficient in caveats.\n\n"
        f"EXPECTED SCHEMA:\n{json.dumps(output_schema)}\n\n"
        "RETURN ONLY JSON NOW."
    )

    client = boto3.client("bedrock-runtime", region_name=_region())
    text, payload = _invoke_text(client, model_id, prompt, max_gen_len, temperature, top_p)
    if not text:
        return {"error": "Bedrock returned empty generation.", "raw": payload}

    parsed = _parse_model_output(text)
    if parsed is not None:
        return parsed

    # Retry once with a tighter prompt to reduce truncation and format drift.
    retry_prompt = (
        f"{system}\n\n"
        "RETRY TASK:\n"
        "Your previous response was invalid or truncated.\n"
        "Return STRICT JSON only, minified on one line, with keys exactly: summary,key_drivers,peer_context,caveats.\n"
        "Use 2 to 4 key_drivers with short why_it_matters fields.\n\n"
        "FACTUAL PACKET (JSON):\n"
        f"{json.dumps(packet, ensure_ascii=False)}\n\n"
        "RETURN ONLY JSON NOW."
    )
    retry_text, retry_payload = _invoke_text(
        client=client,
        model_id=model_id,
        prompt=retry_prompt,
        max_gen_len=max(350, int(max_gen_len * 0.75)),
        temperature=min(temperature, 0.1),
        top_p=top_p,
    )
    retry_parsed = _parse_model_output(retry_text)
    if retry_parsed is not None:
        return retry_parsed

    return {
        "error": "Model did not return valid JSON.",
        "raw": text,
        "retry_raw": retry_text,
        "raw_response": payload,
        "retry_raw_response": retry_payload,
    }

