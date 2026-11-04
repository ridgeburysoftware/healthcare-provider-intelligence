# provider_graph/pipeline.py
from __future__ import annotations

from typing import Optional
from neo4j import GraphDatabase

from .config import Config
from .io_arrow import read_long_features, read_unified
from .features import build_signature_matrix
from .similarity import compute_similarity_and_communities
from .neo import build_payloads, neo_write, clear_run_relationships

PROVIDER_MERGE = """
UNWIND $rows AS r
MERGE (:Provider {npi:r.npi})
"""

COMMUNITY_MERGE = """
UNWIND $rows AS r
MERGE (c:Community {run_id:r.run_id, id:r.id})
ON CREATE SET c.created_at = r.created_at
"""

SIMILAR_TO_MERGE = """
UNWIND $rows AS r
MATCH (a:Provider {npi:r.a})
MATCH (b:Provider {npi:r.b})
MERGE (a)-[rel:SIMILAR_TO {run_id:r.run_id}]->(b)
SET rel.sim = r.sim
"""

IN_COMMUNITY_MERGE = """
UNWIND $rows AS r
MATCH (p:Provider {npi:r.npi})
MATCH (c:Community {run_id:r.run_id, id:r.cid})
MERGE (p)-[rel:IN_COMMUNITY {run_id:r.run_id}]->(c)
SET rel.drift_score = r.drift_score,
    rel.top_peers   = r.top_peers
"""

def run(cfg: Config, use_faiss: bool = True) -> None:
    drugs = read_long_features(cfg.drugs_s3, cfg.year)
    hcpcs = read_long_features(cfg.hcpcs_s3, cfg.year)
    unified = read_unified(cfg.unified_s3, cfg.year, cfg.scalar_cols)

    V, npis = build_signature_matrix(
        drugs=drugs,
        hcpcs=hcpcs,
        unified=unified,
        top_d=cfg.top_d,
        top_b=cfg.top_b,
        include_scalars=cfg.include_scalars,
        scalar_cols=cfg.scalar_cols,
    )

    sim = compute_similarity_and_communities(
        V, npis,
        top_k=cfg.top_k,
        sim_threshold=cfg.sim_threshold,
        top_peers=cfg.top_peers,
        random_state=cfg.random_state,
        use_faiss=use_faiss,
    )

    payloads = build_payloads(cfg.run_id, npis, sim.edges, sim.provider_rows, sim.partition)

    driver = GraphDatabase.driver(cfg.neo4j_uri, auth=(cfg.neo4j_user, cfg.neo4j_pass))
    try:
        neo_write(driver, cfg.neo4j_db, PROVIDER_MERGE, payloads.providers, cfg.write_batch)
        neo_write(driver, cfg.neo4j_db, COMMUNITY_MERGE, payloads.communities, cfg.write_batch)
        clear_run_relationships(driver, cfg.neo4j_db, cfg.run_id)
        neo_write(driver, cfg.neo4j_db, SIMILAR_TO_MERGE, payloads.similar_to, cfg.write_batch)
        neo_write(driver, cfg.neo4j_db, IN_COMMUNITY_MERGE, payloads.in_community, cfg.write_batch)
    finally:
        driver.close()
