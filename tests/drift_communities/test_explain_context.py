from __future__ import annotations

import pandas as pd

from drift_communities import explain_context as ec


def _raw(fn):
    # Streamlit cache decorators wrap callables; tests invoke undecorated logic.
    return getattr(fn, "__wrapped__", fn)


def test_evidence_snapshot_metrics_basic():
    ctx = {
        "peers": [{"sim": 0.9}, {"sim": 0.7}],
        "hcpcs": [
            {"delta_allowed": 100.0, "allowed": 300.0},
            {"delta_allowed": -50.0, "allowed": 100.0},
        ],
        "drugs": [
            {"delta_spend": 40.0, "spend": 100.0},
            {"delta_spend": 10.0, "spend": 50.0},
        ],
    }

    out = ec.evidence_snapshot_metrics(ctx)
    assert out["peers_used"] == 2
    assert out["avg_similarity"] == 0.8
    assert out["top_deltas_sum"] == 200.0
    assert round(out["top_share"], 4) == round(300.0 / 400.0, 4)


def test_build_explain_context_missing_npi():
    out = _raw(ec.build_explain_context)("RUN_1", 1, "")
    assert out == {"error": "Missing npi"}


def test_build_explain_context_provider_not_found(monkeypatch):
    # Simulate zero rows from Neo4j membership query.
    monkeypatch.setattr(ec, "run_cypher", lambda *args, **kwargs: [])
    out = _raw(ec.build_explain_context)("RUN_1", 1, "123")
    assert "error" in out
    assert "Provider 123 not found" in out["error"]


def test_build_explain_context_happy_path(monkeypatch):
    def fake_run_cypher(q, **kwargs):  # pylint: disable=unused-argument
        # Return deterministic payloads for membership + peer lookup queries.
        if "RETURN p.npi AS npi" in q:
            return [{"npi": "123", "community_id": 7, "drift_score": 0.66}]
        if "RETURN peer_npi, sim" in q:
            return [{"peer_npi": "999", "sim": 0.8}, {"peer_npi": "888", "sim": 0.5}]
        return []

    monkeypatch.setattr(ec, "run_cypher", fake_run_cypher)
    monkeypatch.setattr(
        ec,
        "top_hcpcs_for_provider",
        lambda npi, k=10: pd.DataFrame([{"id": "A100", "label": "HCPCS A100", "allowed": 120.0, "count": 10.0}]),
    )
    monkeypatch.setattr(
        ec,
        "top_drugs_for_provider",
        lambda npi, k=10: pd.DataFrame([{"id": "D100", "label": "Drug D100", "spend": 200.0, "count": 4.0}]),
    )
    monkeypatch.setattr(
        ec,
        "peer_baseline_hcpcs",
        lambda peer_npis, hcpcs_codes: pd.DataFrame(
            [{"id": "A100", "peer_allowed_avg": 100.0, "peer_count_avg": 8.0}]
        ),
    )
    monkeypatch.setattr(
        ec,
        "peer_baseline_drugs",
        lambda peer_npis, drug_ids: pd.DataFrame(
            [{"id": "D100", "peer_spend_avg": 150.0, "peer_count_avg": 2.0}]
        ),
    )

    # Full context assembly with mocked provider features and peer baselines.
    out = _raw(ec.build_explain_context)("RUN_1", 7, "123", peers_k=2, drivers_k=1)

    assert out["provider"]["npi"] == "123"
    assert out["provider"]["band"] == "RED"
    assert len(out["peers"]) == 2
    assert out["hcpcs"][0]["delta_allowed"] == 20.0
    assert out["drugs"][0]["delta_spend"] == 50.0
