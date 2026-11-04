# Healthcare Provider Intelligence

A Ridgebury Software engineering portfolio application for exploring provider similarity communities, service/drug evidence, and differences from similarity peers.

The repository includes the React review workspace, FastAPI backend, original Streamlit interface, FAISS similarity/Louvain community pipeline, Neo4j query and graph-writing modules, AWS Glue transformation jobs, tests, and architecture diagrams.

## Technology

Python, FastAPI, React, Vite, Tailwind CSS, Neo4j/Cypher, FAISS, NumPy, pandas, PyArrow, NetworkX, python-louvain, Streamlit, Plotly, and Docker Compose. Optional AI explanation adapters use Amazon Bedrock and OpenAI; the React API's explanation action uses Bedrock. Model actions are disabled while no model is configured.

## Standalone local setup

Install Docker with Compose and Python 3.11+:

```sh
python scripts/configure_local.py
docker compose up -d --build
```

- Review app: **http://127.0.0.1:8520**
- Neo4j Browser: **http://127.0.0.1:17474**
- Local Bolt endpoint: **bolt://127.0.0.1:17687**

The setup script generates a private password only in this repository's ignored `.env`. Compose uses the project name `healthcare-provider-intelligence` and a separate graph volume. It never reads, starts, inspects, mounts, or restores the original application's database or credentials.

**The graph starts empty.** The preserved CMS-derived analysis and database dump from the original installation are not part of this source repository. The UI reports that no analysis is available until an explicitly prepared dataset has been loaded. The historical 14,916 memberships/18 communities are not promised for a fresh checkout.

## Development

Use an independent virtual environment and the frontend's own lockfile:

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements-dev.txt
npm ci --prefix frontend --ignore-scripts
npm run build --prefix frontend
python scripts/run_local.py
```

Start only this repository's graph first with `docker compose up -d graph`. The launcher reads this workspace's `.env` or explicitly provided environment settings. It does not inspect the old `neo4j` container. The retained Streamlit UI is available with `python scripts/run_local.py --legacy` on port **8521**.

Frontend development uses `npm run dev --prefix frontend` on port **5190**, proxying API requests to 8520.

## Tests

```sh
python -m pytest
npm run build --prefix frontend
```

Tests include the existing query/evidence and graph-writing unit tests, pipeline tests, an actual FAISS native-path check on synthetic vectors, and API checks with synthetic query responses. They do not need a production database, CMS download, AWS account, or model call.

## Graph pipeline and data

`pipelines/ecs_build/provider_graph/` builds provider feature signatures, searches cosine-similarity peers with FAISS, runs Louvain community detection, computes drift scores, and writes run-scoped relationships to Neo4j. Install `requirements-pipeline.txt` to run it outside the development environment.

`pipelines/glue/jobs/` contains the source project's AWS Glue/PySpark transformations; those jobs need their managed AWS runtime. The graph pipeline requires explicitly supplied `DRUGS_S3`, `HCPCS_S3`, `UNIFIED_S3`, run settings, and Neo4j credentials. No production S3 location, AWS credentials, Terraform state, or database dump is included. `scripts/seed_neo4j.py` is a retained data-loading utility that requires separately supplied parquet files and explicit database settings; it is not run during startup.

## Provenance and scope

Extracted from RidgefieldSoftware commit `0440f1ecb192e95dd926d69b88b5c3bb08a99a90` with a fresh repository history. See [SOURCE-PROVENANCE.json](SOURCE-PROVENANCE.json) and [EXTRACTION-REPORT.md](EXTRACTION-REPORT.md). The original checkout, existing containers, graph, and other apps are unchanged.

The account-specific AWS infrastructure, old cloud marketing site, private runbook, and original S3 dump-restoration container were excluded. Architecture diagrams remain under `docs/`. No cloud infrastructure or public application deployment was performed.

Drift and similarity differences do not establish fraud, clinical appropriateness, or compliance. This repository does not grant a new open-source license for original project code; third-party dependencies retain their licenses.
