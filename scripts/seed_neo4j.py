import os
import math
import pandas as pd
from neo4j import GraphDatabase

# Adjust these paths to match your repo (these look like what you used earlier)
UNIFIED = "data/derived/oncology_provider_2023_unified_geo_v2.parquet"
PARTD   = "data/derived/oncology_partd_2023_provider_drugs.parquet"
PARTB   = "data/derived/oncology_partb_2023_provider_hcpcs.parquet"

NEO4J_URI  = os.environ["NEO4J_URI"]
NEO4J_USER = os.environ["NEO4J_USER"]
NEO4J_PASS = os.environ["NEO4J_PASSWORD"]

BATCH = int(os.getenv("BATCH", "1000"))

def chunker(df, n):
    for i in range(0, len(df), n):
        yield df.iloc[i:i+n]

def main():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))

    # 1) Constraints / indexes
    with driver.session() as s:
        s.run("CREATE CONSTRAINT provider_npi IF NOT EXISTS FOR (p:Provider) REQUIRE p.npi IS UNIQUE")
        s.run("CREATE CONSTRAINT drug_id IF NOT EXISTS FOR (d:Drug) REQUIRE d.drug IS UNIQUE")
        s.run("CREATE CONSTRAINT hcpcs_id IF NOT EXISTS FOR (h:HCPCS) REQUIRE h.hcpcs IS UNIQUE")

    # 2) Providers
    prov = pd.read_parquet(UNIFIED)
    # Expect at least: npi, state, zip3, matched_taxonomy, confidence_badge, combined_outlier_score, etc.
    prov = prov.fillna("")

    prov_rows = prov.to_dict("records")
    with driver.session() as s:
        for batch in chunker(prov, BATCH):
            s.run("""
            UNWIND $rows AS r
            MERGE (p:Provider {npi: toString(r.npi)})
            SET p.state = r.state,
                p.zip3  = toString(r.zip3),
                p.taxonomy = r.matched_taxonomy,
                p.confidence = r.combined_confidence,
                p.outlier_score = r.combined_outlier_score
            """, rows=batch.to_dict("records"))

    # 3) Part D provider -> drug edges
    partd = pd.read_parquet(PARTD).fillna("")
    # Expect at least: npi, drug (or drug_name)
    # If your column name differs, change here:
    if "drug" not in partd.columns and "drug_name" in partd.columns:
        partd = partd.rename(columns={"drug_name": "drug"})

    with driver.session() as s:
        for batch in chunker(partd, BATCH):
            s.run("""
            UNWIND $rows AS r
            MERGE (p:Provider {npi: toString(r.npi)})
            MERGE (d:Drug {drug: toString(r.drug)})
            MERGE (p)-[rel:PRESCRIBES]->(d)
            """, rows=batch.to_dict("records"))

    # 4) Part B provider -> HCPCS edges
    partb = pd.read_parquet(PARTB).fillna("")
    if "hcpcs" not in partb.columns and "hcpcs_code" in partb.columns:
        partb = partb.rename(columns={"hcpcs_code": "hcpcs"})

    with driver.session() as s:
        for batch in chunker(partb, BATCH):
            s.run("""
            UNWIND $rows AS r
            MERGE (p:Provider {npi: toString(r.npi)})
            MERGE (h:HCPCS {hcpcs: toString(r.hcpcs)})
            MERGE (p)-[rel:BILLS]->(h)
            """, rows=batch.to_dict("records"))

    driver.close()
    print("✅ Neo4j seeded.")

if __name__ == "__main__":
    main()
