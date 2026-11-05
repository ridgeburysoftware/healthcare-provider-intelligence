# Healthcare Provider Intelligence

A Ridgebury Software engineering portfolio application for exploring provider similarity communities, service/drug evidence, and differences from similarity peers.

The repository includes the React review workspace, FastAPI backend, original Streamlit interface, FAISS similarity/Louvain community pipeline, Neo4j query and graph-writing modules, AWS Glue transformation jobs, tests, and architecture diagrams.

## Technology

Python, FastAPI, React, Vite, Tailwind CSS, Neo4j/Cypher, FAISS, NumPy, pandas, PyArrow, NetworkX, python-louvain, Streamlit, Plotly, and Docker Compose. Optional AI explanations use OpenAI by default; Amazon Bedrock remains available through explicit configuration. Explanations describe recorded evidence and do not change drift scores, communities, or query results. Model actions are disabled while the selected provider is not configured.

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

## Optional OpenAI explanations

Set `AI_PROVIDER=openai` and `OPENAI_API_KEY` in the server environment or this workspace's ignored `.env`. `OPENAI_MODEL` defaults to the existing adapter's `gpt-4o-mini` and can be overridden. Restart the local app (or recreate the app container) after changing configuration. Never use a `VITE_` variable for the key or commit credentials.

Select a provider and click **Explain selected provider**. Only this action calls OpenAI; loading pages, browsing the graph, and exporting evidence do not. The Responses API receives a bounded factual packet with provider/peer identifiers, the stored drift score, and up to ten recorded service/drug comparisons. It uses structured output, `store=false`, a 30-second SDK timeout, and no automatic SDK retries. Driver identifiers and numbers in the response are copied from supplied evidence after validating model-selected indexes. Free-text interpretation remains AI-generated and should be checked against the evidence.

Missing configuration disables the button. Missing comparison evidence produces an insufficient-evidence result without a model call. Provider failures show a recoverable message; analytics remain available. The API advertises only the selected provider name and availability, never the key.

To use the original AWS adapter instead, set `AI_PROVIDER=bedrock` with `BEDROCK_MODEL_ID` and AWS credentials. Set `AI_PROVIDER=none` to disable explanations even when credentials are present. The original Streamlit interface retains its own provider selector.

API reference: [OpenAI Responses](https://developers.openai.com/api/reference/python/resources/responses/methods/create).

## Tests

```sh
python -m pytest
npm run build --prefix frontend
```

Tests include the existing query/evidence and graph-writing unit tests, pipeline tests, an actual FAISS native-path check on synthetic vectors, and API checks with synthetic query responses. They do not need a production database, CMS download, AWS account, or model call.

## Graph pipeline and data

`pipelines/ecs_build/provider_graph/` builds provider feature signatures, searches cosine-similarity peers with FAISS, runs Louvain community detection, computes drift scores, and writes run-scoped relationships to Neo4j. Install `requirements-pipeline.txt` to run it outside the development environment.

`pipelines/glue/jobs/` contains the source project's AWS Glue/PySpark transformations; those jobs need their managed AWS runtime. The graph pipeline requires explicitly supplied `DRUGS_S3`, `HCPCS_S3`, `UNIFIED_S3`, run settings, and Neo4j credentials. No production S3 location, AWS credentials, Terraform state, or database dump is included. `scripts/seed_neo4j.py` is a retained data-loading utility that requires separately supplied parquet files and explicit database settings; it is not run during startup.

## Original AWS infrastructure

The historical [ECS/Fargate and Glue Terraform](infra/aws/README.md) is included with account-specific settings replaced by inputs. It documents the original AWS implementation; the current React/FastAPI demo uses a separate deployment. See the [generated dependency diagrams](docs/terraform/README.md) and the infrastructure README for prerequisites, retained historical limitations, and local validation commands.

## Provenance and scope

Extracted from RidgefieldSoftware commit `0440f1ecb192e95dd926d69b88b5c3bb08a99a90` with a fresh repository history. See [SOURCE-PROVENANCE.json](SOURCE-PROVENANCE.json) and [EXTRACTION-REPORT.md](EXTRACTION-REPORT.md). The original checkout, existing containers, graph, and other apps are unchanged.

The original extraction excluded AWS infrastructure; a later publication pass added the ECS/Fargate and Glue Terraform under `infra/aws/` with deployment-specific inputs. The old cloud marketing site, private runbook, and original S3 dump-restoration container remain excluded. Terraform dependency diagrams remain under `docs/terraform/`. No cloud infrastructure or public application deployment was performed.

Drift and similarity differences do not establish fraud, clinical appropriateness, or compliance. This repository does not grant a new open-source license for original project code; third-party dependencies retain their licenses.
