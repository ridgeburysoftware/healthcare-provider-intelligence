from __future__ import annotations

import builtins

from drift_communities import llm_bedrock as lb


def test_looks_like_arn_or_profile():
    assert lb._looks_like_arn_or_profile("arn:aws:bedrock:us-east-1:123:inference-profile/x")
    assert lb._looks_like_arn_or_profile("meta.llama3-70b-instruct-v1:0")
    assert lb._looks_like_arn_or_profile("us.meta.llama3-2-11b-instruct-v1:0")
    assert not lb._looks_like_arn_or_profile("gpt-4o-mini")


def test_extract_json_object():
    # Model output may include prose around JSON; parser should recover first object.
    text = "prefix {\"a\": 1, \"b\": [2,3]} suffix"
    assert lb._extract_json_object(text) == "{\"a\": 1, \"b\": [2,3]}"
    assert lb._extract_json_object("no object here") is None


def test_severity_bucket():
    assert lb._severity_bucket(None, 100.0) == "unknown"
    assert lb._severity_bucket(10.0, 100.0) == "small"
    assert lb._severity_bucket(100.0, 100.0) == "material"
    assert lb._severity_bucket(300.0, 100.0) == "extreme"


def test_driver_candidate_rows_orders_by_delta_abs():
    # Rows should be sorted by absolute signal size across HCPCS + Drug features.
    ctx = {
        "hcpcs": [
            {"id": "H1", "label": "HCPCS H1", "allowed": 110, "peer_allowed_avg": 100, "delta_allowed": 10},
            {"id": "H2", "label": "HCPCS H2", "allowed": 300, "peer_allowed_avg": 100, "delta_allowed": 200},
        ],
        "drugs": [
            {"id": "D1", "label": "Drug D1", "spend": 60, "peer_spend_avg": 100, "delta_spend": -40},
        ],
    }

    rows = lb._driver_candidate_rows(ctx, k=5)
    assert [r["id"] for r in rows] == ["H2", "D1", "H1"]
    assert rows[0]["type"] == "HCPCS"
    assert rows[1]["type"] == "Drug"
    assert rows[2]["evidence"]["delta"] == 10.0


def test_parse_json_with_langchain_import_error(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("langchain_core"):
            raise ImportError("not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert lb._parse_json_with_langchain('{"a":1}') is None


def test_parse_model_output_recovers_markdown_fenced_json():
    # Integration-style parser path: fenced JSON should still parse as an object.
    text = '```json\n{"summary":"ok","key_drivers":[],"peer_context":{"peers_used":[],"interpretation":""},"caveats":[]}\n```'
    parsed = lb._parse_model_output(text)
    assert parsed is not None
    assert parsed["summary"] == "ok"
