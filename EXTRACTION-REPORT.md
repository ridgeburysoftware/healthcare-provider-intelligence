# Provider Intelligence Extraction Report

Date: November 4, 2026.

## Source and contents

Extracted 55 tracked application files from `healthcare-demo/` at RidgefieldSoftware commit `0440f1ecb192e95dd926d69b88b5c3bb08a99a90`. The application folder was flattened into this standalone repository root.

Included:

- React/Vite/Tailwind review UI and its lockfile.
- FastAPI review API and the original Streamlit interface.
- Neo4j/Cypher queries, graph visualization, peer evidence, and explanation adapters.
- FAISS similarity search, feature-signature construction, Louvain communities, drift scoring, and run-scoped Neo4j graph writes.
- AWS Glue feature/vector transformation job source.
- Existing unit tests and architecture/data-model diagrams.

Excluded:

- Other applications, consultancy website, and private Git history.
- The preserved Neo4j database, real saved analysis, S3 dumps, and data files.
- Credentials, ignored files, dependency environments, and caches.
- The old marketing-site project, account-specific Terraform/cloud deployment configuration, private deployment runbook, and original S3 database-restoration container.

## Standalone adaptations

- Separate Compose project: `healthcare-provider-intelligence`.
- App port 8520, optional Streamlit port 8521, Neo4j HTTP port 17474, and Bolt port 17687.
- Independent `provider-graph-data` volume under the new Compose project name; no original bind mounts or external volumes.
- New local configuration script creates a password only in this repository's ignored `.env`, preserving an existing configured password on later runs.
- Replaced the recovery launcher that started/inspected the old `neo4j` container. The standalone launcher loads local settings and starts only the requested Python interface. Starting the new graph remains an explicit Compose action.
- Updated the direct Neo4j fallback URI and Vite API proxy to the standalone ports.
- Renamed frontend package metadata and its development port; retained the UI, styling, query semantics, FAISS algorithm, and pipeline logic.
- Separated UI/API, pipeline, and development requirements using direct package versions from the source application's working environment. The unrelated shared baseball-data dependency is not required. Transitive Python dependencies remain pip-resolved rather than fully hash-locked.
- Added an actual native-FAISS synthetic-vector check and API tests that require no real database or provider call.

## Validation

| Check | Result |
|---|---|
| React production build | PASS |
| Frontend dependency audit | No vulnerabilities reported during installation |
| Independent Python installation and `pip check` | PASS, no broken requirements |
| Existing and added Python tests | PASS, 24 tests |
| Native FAISS branch | PASS, synthetic vectors, similarity edges and communities |
| API tests | PASS, synthetic overview, empty-analysis response, and disabled-explanation guard |
| FastAPI serving built React HTML and assets | PASS |
| Python source syntax | PASS |
| Independent Compose configuration | PASS, correct new ports, graph endpoint and volume namespace |
| Local credential setup | PASS, idempotent; `.env` excluded from Git |
| Publication pattern scan | No private-key/token, original private-host, personal-path, or AWS-account-number matches in the selected files |
| Original source preservation | PASS, all 1,043 tracked files, HEAD and pre-existing Git status unchanged |

The FAISS test emits three upstream SWIG deprecation warnings. The direct API static-page smoke check also logs expected Streamlit cache notices outside a Streamlit runtime. Neither caused a test failure.

No production graph was read, copied, restarted, or modified. No model call, cloud provisioning, full CMS data-pipeline execution, or public app deployment was performed. Docker Compose configuration was validated; a full Docker image build/live Neo4j integration was not claimed.

## Data boundary

A fresh graph is empty. The historical analysis containing 14,916 provider memberships across 18 communities remains in the original installation. Source tests use synthetic inputs and do not manufacture those historical results. To populate this new graph, separately prepare and explicitly load an appropriate dataset using the retained pipeline and data-loading utilities.

The original cloud account/deployment assets can be reviewed separately if a future infrastructure extraction is requested.
