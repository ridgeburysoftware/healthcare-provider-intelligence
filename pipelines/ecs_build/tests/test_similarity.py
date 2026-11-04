# tests/test_similarity.py
import pandas as pd
from provider_graph.similarity import compute_similarity_and_communities

def test_similarity_builds_edges_and_partition_small():
    # Make providers 1 & 2 very similar; 3 different
    V = pd.DataFrame(
        [
            [1.0, 0.9],
            [1.0, 0.85],
            [0.0, 1.0],
        ],
        index=["0000000001","0000000002","0000000003"],
        columns=["f1","f2"]
    )
    npis = list(V.index)

    res = compute_similarity_and_communities(
        V, npis,
        top_k=2,
        sim_threshold=0.8,
        top_peers=2,
        random_state=42,
        use_faiss=False,   # pure numpy KNN for unit test
    )

    assert len(res.partition) == 3
    # Should have at least one edge among similar nodes
    assert any((i == 0 and j == 1) or (i == 1 and j == 0) for (i,j,_) in res.edges)
    # provider_rows shape
    assert len(res.provider_rows) == 3
    npi0, cid0, drift0, peers0 = res.provider_rows[0]
    assert npi0 == "0000000001"
