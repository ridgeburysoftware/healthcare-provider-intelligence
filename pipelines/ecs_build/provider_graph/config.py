# provider_graph/config.py
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

@dataclass(frozen=True)
class Config:
    run_id: str
    year: int

    drugs_s3: str
    hcpcs_s3: str
    unified_s3: str

    top_d: int
    top_b: int
    top_k: int
    sim_threshold: float
    top_peers: int

    include_scalars: bool
    scalar_cols: List[str]

    neo4j_uri: str
    neo4j_user: str
    neo4j_pass: str
    neo4j_db: str
    write_batch: int
    random_state: int

def _req(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v

def from_env() -> Config:
    run_id = os.environ.get("RUN_ID", "RUN_2023_01")
    year = int(os.environ.get("YEAR", "2023"))

    def norm_root(x: str) -> str:
        return x.rstrip("/") + "/"

    drugs_s3 = norm_root(_req("DRUGS_S3"))
    hcpcs_s3 = norm_root(_req("HCPCS_S3"))
    unified_s3 = norm_root(_req("UNIFIED_S3"))

    top_d = int(os.environ.get("TOP_D", "25"))
    top_b = int(os.environ.get("TOP_B", "25"))
    top_k = int(os.environ.get("TOP_K", "25"))
    sim_threshold = float(os.environ.get("SIM_THRESHOLD", "0.35"))
    top_peers = int(os.environ.get("TOP_PEERS", "8"))

    include_scalars = bool(int(os.environ.get("INCLUDE_SCALARS", "1")))
    scalar_cols = [
        c.strip() for c in os.environ.get(
            "SCALAR_COLS",
            "allowed_per_service,cost_per_claim,combined_outlier_score"
        ).split(",") if c.strip()
    ]

    neo4j_uri = _req("NEO4J_URI")
    neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
    neo4j_pass = _req("NEO4J_PASS")
    neo4j_db = os.environ.get("NEO4J_DB", "neo4j")

    write_batch = int(os.environ.get("WRITE_BATCH", "2000"))
    random_state = int(os.environ.get("RANDOM_STATE", "42"))

    return Config(
        run_id=run_id, year=year,
        drugs_s3=drugs_s3, hcpcs_s3=hcpcs_s3, unified_s3=unified_s3,
        top_d=top_d, top_b=top_b, top_k=top_k,
        sim_threshold=sim_threshold, top_peers=top_peers,
        include_scalars=include_scalars, scalar_cols=scalar_cols,
        neo4j_uri=neo4j_uri, neo4j_user=neo4j_user, neo4j_pass=neo4j_pass, neo4j_db=neo4j_db,
        write_batch=write_batch, random_state=random_state,
    )
