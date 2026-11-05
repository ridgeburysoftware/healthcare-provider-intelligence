# Healthcare Provider Intelligence

## Project overview and capabilities

A public engineering portfolio project by **Ridgebury Software**, demonstrating healthcare data pipelines, graph analytics, vector similarity, and optional AI-assisted evidence review.

The project combines CMS provider utilization data with provider similarity communities and recorded service/drug comparisons. It includes the current React/FastAPI review application, the original Streamlit interface, Python analysis pipelines, and the original AWS infrastructure source.

Capabilities demonstrated:

- Transform CMS Medicare Part B, Part D, and provider reference data into analysis-ready datasets.
- Build provider feature signatures, find similarity peers with FAISS, and detect communities with Louvain.
- Store run-scoped provider relationships, communities, and utilization evidence in Neo4j.
- Explore the peer graph, inspect provider drift scores, review underlying comparisons, and export evidence.
- Generate optional AI explanations from recorded evidence without changing analytics or scores.

This repository presents the implementation and engineering artifacts. The populated demonstration uses separately prepared data; a source checkout does not include that analysis. Drift and similarity differences do not establish fraud, clinical appropriateness, or compliance.

## Application screenshots

**Provider review workspace** — peer communities, a similarity graph, and the selected provider's recorded drift score.

![Healthcare Provider Intelligence review workspace and provider similarity graph](https://ridgeburysoftware.com/assets/provider-intelligence-workspace.png)

## Original AWS architecture and deployment

The original implementation ran on AWS. Glue/PySpark jobs transformed CMS data into S3 datasets; the Python/FAISS pipeline built similarity relationships and communities for Neo4j. The original Streamlit application ran on ECS/Fargate, with Bedrock providing optional generative AI integration.

![Original Provider Intelligence AWS architecture](https://ridgeburysoftware.com/assets/provider-intelligence-architecture.svg)

The infrastructure source includes ECS/Fargate, an Application Load Balancer, VPC networking and endpoints, EFS-backed Neo4j storage, service discovery, IAM, CloudWatch, Glue catalogs/crawlers/jobs, and an Athena workgroup.

- [AWS Terraform documentation and deployment assumptions](infra/aws/README.md)
- [ECS/Fargate configuration](infra/aws/ecs/)
- [Glue configuration](infra/aws/glue/)
- [Generated Terraform dependency diagrams](docs/terraform/README.md)

The current React/FastAPI demonstration is hosted independently of AWS and uses OpenAI for optional evidence explanations. The historical AWS Terraform describes the original deployment and does not configure the current hosted demo. The architecture image provides a platform overview; the dependency diagrams are generated directly from the retained Terraform resource definitions.

## Technical implementation and technology stack

| Engineering area | Implementation | Source |
| --- | --- | --- |
| Data engineering | AWS Glue, PySpark, S3, Parquet, pandas, and PyArrow for CMS ingestion and feature preparation | [`pipelines/glue/jobs/`](pipelines/glue/jobs/) |
| Vector and community analysis | Python, NumPy, FAISS, NetworkX, and python-louvain for similarity search, peer communities, and drift scoring | [`provider_graph/`](pipelines/ecs_build/provider_graph/) |
| Graph storage and retrieval | Neo4j/Cypher for provider relationships, run-scoped analysis, and utilization evidence | [`queries.py`](src/drift_communities/queries.py), [`neo.py`](pipelines/ecs_build/provider_graph/neo.py) |
| Review application | React, Vite, Tailwind CSS, and FastAPI for graph exploration and evidence review | [`frontend/`](frontend/), [`api.py`](src/drift_communities/api.py) |
| AI explanations | OpenAI Responses API in the current application; Amazon Bedrock adapter retained from AWS | [`ai.py`](src/drift_communities/ai.py), [`llm_openai.py`](src/drift_communities/llm_openai.py), [`llm_bedrock.py`](src/drift_communities/llm_bedrock.py) |
| Infrastructure and packaging | Terraform, ECS/Fargate, Docker, and Docker Compose | [`infra/aws/`](infra/aws/), [`Dockerfile`](Dockerfile), [`compose.yaml`](compose.yaml) |
| Original interface | Streamlit and Plotly | [`app.py`](src/drift_communities/app.py) |

The graph pipeline constructs provider feature signatures, searches cosine-similarity peers, runs Louvain community detection, computes drift scores, and writes analysis relationships to Neo4j. The application retrieves those stored results rather than rebuilding the analysis on each request.

Optional AI explanations receive a bounded packet of provider/peer identifiers, the stored drift score, and recorded service/drug comparisons. The OpenAI adapter uses structured responses, validates evidence references, and copies driver values from the supplied evidence. Free-text interpretation remains AI-generated; it does not change community membership, drift scores, or query results.

## Live demonstration link

**[Open Healthcare Provider Intelligence](https://ridgeburysoftware.com/demos/providers/)**

The hosted demonstration uses a separately prepared CMS-derived analysis and populated Neo4j database. It provides the review workflow illustrated above without requiring visitors to prepare the data locally.

[Project page and architecture overview](https://ridgeburysoftware.com/projects/provider-intelligence/)

## Local development and setup requirements

Local setup is available for developers inspecting or extending the implementation. **On a fresh checkout, running Docker Compose starts the application services and an empty Neo4j database; it does not produce the populated demonstration.**

### Data required for meaningful functionality

Reproducing the analysis and review workflows requires:

1. **CMS provider datasets:** Medicare Part B utilization, Part D prescribing, and provider reference data used by the transformations.
2. **Processed analysis artifacts:** compatible feature/vector datasets and generated provider similarity, community, and drift results for a selected analysis run.
3. **Populated Neo4j data:** provider and utilization records plus the corresponding run-scoped communities, memberships, similarity relationships, and evidence used by the API.

Source datasets and processed artifacts are needed to reproduce or rebuild the analysis. The review application's request path reads the populated graph; it does not read raw CMS files or run the ingestion pipeline during startup. Without the required graph data, the UI reports that no analysis is available and cannot provide meaningful provider comparisons.

CMS datasets, generated FAISS indexes, processed analysis outputs, and the preserved demonstration database/dump are not included. Local startup does not download CMS data, process it, restore the hosted database, or seed an example analysis. The hosted demo's displayed counts should not be expected from a fresh checkout.

### Tooling and container setup

Requirements: Docker with Compose and Python 3.11+. Source-based frontend development also needs Node.js/npm; the Docker frontend build uses Node 22.

```sh
python scripts/configure_local.py
docker compose up -d --build
```

- Local review app: **http://127.0.0.1:8520**
- Neo4j Browser: **http://127.0.0.1:17474**
- Local Bolt endpoint: **bolt://127.0.0.1:17687**

The configuration script generates a password in this workspace's ignored `.env`. Compose uses a separate `healthcare-provider-intelligence` project and graph volume. It does not inspect or restore another application's database. These commands prepare the runtime only; populate compatible graph data separately before expecting the review workflows to function.

### Developing from source

Use the graph service only for this development mode. If the Compose application is already running, stop its `app` service before starting the Python server on the same port.

```sh
python scripts/configure_local.py
docker compose up -d graph
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements-dev.txt
npm ci --prefix frontend --ignore-scripts
npm run build --prefix frontend
python scripts/run_local.py
```

The launcher reads this workspace's `.env` or explicitly provided environment settings. Frontend development uses `npm run dev --prefix frontend` on port **5190**, proxying API requests to 8520. The original Streamlit interface remains available with `python scripts/run_local.py --legacy` on port **8521** and has the same underlying data requirements.

### Preparing analysis data

The Glue jobs under `pipelines/glue/jobs/` require their AWS Glue/PySpark runtime and explicitly supplied data paths and job arguments. The modular graph pipeline is under `pipelines/ecs_build/provider_graph/`; install `requirements-pipeline.txt` to run it outside the development environment. It requires `DRUGS_S3`, `HCPCS_S3`, `UNIFIED_S3`, run settings, and Neo4j connection settings. See [`config.py`](pipelines/ecs_build/provider_graph/config.py) for its inputs.

[`scripts/seed_neo4j.py`](scripts/seed_neo4j.py) is a retained loader for separately prepared parquet files. Its expected paths/schema and `NEO4J_PASSWORD` setting must be supplied explicitly; it is not run by Compose and does not build a complete community analysis by itself. The review app and graph pipeline use `NEO4J_PASS`. Loading and analysis are deliberate developer tasks, not an automated fresh-checkout demonstration.

### Optional AI configuration

Set `AI_PROVIDER=openai` and `OPENAI_API_KEY` in the server environment or this workspace's ignored `.env`. `OPENAI_MODEL` defaults to `gpt-4o-mini` and can be overridden. Restart the app or recreate its container after changing configuration. Keep credentials server-side; never use a `VITE_` variable for a key.

In the React review app, **Explain selected provider** initiates the model request. Browsing the graph, loading pages, and exporting evidence do not call OpenAI. The adapter uses `store=false`, a 30-second SDK timeout, and no automatic SDK retries. Missing configuration disables the action; missing comparison evidence returns an insufficient-evidence result without a model call. Provider errors leave the analytics available.

Set `AI_PROVIDER=bedrock` with `BEDROCK_MODEL_ID` and AWS credentials to use the original AWS adapter. Set `AI_PROVIDER=none` to disable explanations. The original Streamlit interface retains its own provider selector.

### Tests

```sh
python -m pytest
npm run build --prefix frontend
```

Tests use synthetic vectors and mocked query/model responses. They cover native FAISS, feature and graph-writing logic, evidence helpers, API behavior, and explanation handling without a populated demonstration database, CMS download, AWS account, or live model call. Passing these tests does not populate a local analysis.

### Repository data boundary

Keep large CMS datasets, generated FAISS indexes, processed artifacts, secrets, credentials, private environment files, Terraform state/plans, and database dumps outside committed source. Local configuration and data belong in ignored paths such as `.env`, `.local-data/`, or `data/`; verify exclusion before adding generated files. The checked-in `.env.example` contains configuration names without credentials.

## License

This repository does not grant a new open-source license for original project code; third-party dependencies retain their licenses.
