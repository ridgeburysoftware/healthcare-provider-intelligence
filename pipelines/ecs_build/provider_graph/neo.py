# provider_graph/neo.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple
import pandas as pd

@dataclass(frozen=True)
class NeoPayloads:
    providers: List[Dict]
    communities: List[Dict]
    in_community: List[Dict]
    similar_to: List[Dict]

def build_payloads(
    run_id: str,
    npis: List[str],
    edges: List[Tuple[int, int, float]],
    provider_rows: List[Tuple[str, int, float, str]],
    partition: Dict[int, int],
) -> NeoPayloads:
    providers_payload = [{"npi": npi} for npi in npis]

    comm_ids = sorted(set(int(cid) for cid in partition.values()))
    created_at = int(pd.Timestamp.utcnow().timestamp())
    comm_payload = [{"run_id": run_id, "id": int(cid), "created_at": created_at} for cid in comm_ids]

    incomm_payload = [
        {"run_id": run_id, "npi": npi, "cid": int(cid), "drift_score": float(drift), "top_peers": top_peers}
        for (npi, cid, drift, top_peers) in provider_rows
    ]

    sim_payload: List[Dict] = []
    for (i, j, s) in edges:
        a = npis[i]
        b = npis[j]
        sim_payload.append({"run_id": run_id, "a": a, "b": b, "sim": float(s)})
        sim_payload.append({"run_id": run_id, "a": b, "b": a, "sim": float(s)})

    return NeoPayloads(
        providers=providers_payload,
        communities=comm_payload,
        in_community=incomm_payload,
        similar_to=sim_payload,
    )

def neo_write(driver, neo4j_db: str, cypher: str, rows: List[dict], batch_size: int) -> None:
    with driver.session(database=neo4j_db) as sess:
        for i in range(0, len(rows), batch_size):
            sess.run(cypher, rows=rows[i:i + batch_size])

def clear_run_relationships(driver, neo4j_db: str, run_id: str) -> None:
    with driver.session(database=neo4j_db) as sess:
        sess.run("MATCH ()-[r:SIMILAR_TO {run_id:$run_id}]->() DELETE r", run_id=run_id)
        sess.run(
            "MATCH (:Provider)-[r:IN_COMMUNITY {run_id:$run_id}]->(:Community {run_id:$run_id}) DELETE r",
            run_id=run_id
        )
