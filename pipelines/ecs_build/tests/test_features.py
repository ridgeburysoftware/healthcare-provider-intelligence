# tests/test_features.py
import pandas as pd
from provider_graph.features import topn_per_npi, pivot_dense, standardize_scalars, build_signature_matrix

def test_topn_per_npi_keeps_top_values():
    df = pd.DataFrame([
        {"npi":"0000000001","feature_id":"a","value":1.0},
        {"npi":"0000000001","feature_id":"b","value":3.0},
        {"npi":"0000000001","feature_id":"c","value":2.0},
        {"npi":"0000000002","feature_id":"a","value":5.0},
        {"npi":"0000000002","feature_id":"b","value":1.0},
    ])
    out = topn_per_npi(df, 2)
    assert out[out["npi"]=="0000000001"]["feature_id"].tolist() == ["b","c"]
    assert out[out["npi"]=="0000000002"]["feature_id"].tolist() == ["a","b"]

def test_pivot_dense_sums_duplicates():
    df = pd.DataFrame([
        {"npi":"0000000001","feature_id":"x","value":1.0},
        {"npi":"0000000001","feature_id":"x","value":2.0},
        {"npi":"0000000001","feature_id":"y","value":5.0},
    ])
    wide = pivot_dense(df)
    assert float(wide.loc["0000000001","x"]) == 3.0
    assert float(wide.loc["0000000001","y"]) == 5.0

def test_standardize_scalars_zscore_and_prefix():
    u = pd.DataFrame([
        {"npi":"0000000001","allowed_per_service":10.0},
        {"npi":"0000000002","allowed_per_service":20.0},
        {"npi":"0000000003","allowed_per_service":30.0},
    ])
    out = standardize_scalars(u, ["allowed_per_service"])
    assert "S:allowed_per_service" in out.columns
    assert "allowed_per_service" not in out.columns
    # mean ~ 0
    assert abs(out["S:allowed_per_service"].mean()) < 1e-6

def test_build_signature_matrix_orders_by_cohort_and_fills():
    drugs = pd.DataFrame([
        {"npi":"0000000002","feature_id":"d1","value":2.0},
        {"npi":"0000000001","feature_id":"d1","value":1.0},
    ])
    hcpcs = pd.DataFrame([
        {"npi":"0000000001","feature_id":"h1","value":3.0},
    ])
    unified = pd.DataFrame([
        {"npi":"0000000001","allowed_per_service":10.0},
        {"npi":"0000000002","allowed_per_service":20.0},
    ])
    V, npis = build_signature_matrix(drugs, hcpcs, unified, top_d=25, top_b=25, include_scalars=True, scalar_cols=["allowed_per_service"])
    assert npis == ["0000000001","0000000002"]
    assert "d1" in V.columns
    assert "h1" in V.columns
    assert "S:allowed_per_service" in V.columns
    assert float(V.loc["0000000002","h1"]) == 0.0
