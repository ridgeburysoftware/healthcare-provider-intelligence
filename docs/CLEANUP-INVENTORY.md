# Provider Intelligence cleanup inventory

First pass: November 5, 2026. Baseline: `e0b1e48`.

Scope: the standalone public Provider Intelligence repository. This pass does not change the Ridgebury Software website, deployed applications, databases, analytics, or AI behavior. Source provenance remains in [SOURCE-PROVENANCE.json](../SOURCE-PROVENANCE.json); it records the extraction baseline rather than the current file set.

## Removed in the first pass

Repository-wide reference searches covered Python imports and calls, frontend source, launchers, Docker/Compose, requirements, tests, and documentation. Files listed below had no consumers in those entry points.

| File or dependency | Evidence | Action |
| --- | --- | --- |
| `src/drift_communities/explain.py` | Unreferenced older combined implementation of evidence collection, OpenAI explanations, and Streamlit rendering. Current API and Streamlit imports use `explain_context.py`, `llm_openai.py`, and `llm_bedrock.py`; Streamlit rendering lives in `app.py`. | Removed the obsolete module; retained all current implementations. |
| `src/drift_communities/ui_events.py` | Defines `plotly_click_value`, but no code imports the module or calls that function. | Removed the unused click-event wrapper. |
| `streamlit-plotly-events` in `requirements.txt` | Its only import was inside the unused `ui_events.py` wrapper. The current interfaces do not use this package. | Removed the direct requirement. |
| `tools/diag_import_app_main.py` | Standalone diagnostic tries to import `app.main`, which does not exist in this extracted repo. No launcher, test, or documentation invokes it. | Removed the obsolete diagnostic. |
| `requirements-ui.txt` | Unreferenced alternative dependency list inherited from the source application. Docker and documented runtime installation use `requirements.txt`; development and pipeline lists include that file. | Removed the duplicate requirements list; retained the supported dependency files. |
| `docs/about.md` | Empty, unreferenced placeholder. | Removed. |

Removal of an unreferenced module is based on this repository's entry points. This inventory does not claim compatibility with external scripts that import undocumented historical modules.

## Retained application and engineering code

| Area | Entry point or consumer | Decision |
| --- | --- | --- |
| React review workspace | `frontend/src/main.jsx`, Vite; served by `drift_communities.api` | Active application. Keep UI, styles, reusable button, URL helper, and lockfile. |
| FastAPI API | Docker `CMD`, `scripts/run_local.py` | Active backend. Keep routes, queries, graph layout, evidence context, and AI dispatcher. |
| OpenAI adapter | `ai.py`, original Streamlit UI, adapter tests | Active optional AI path. Keep. |
| Bedrock adapter and LangChain parser | AI provider selection, original Streamlit UI, parser tests | Supported optional AWS path. Keep both adapter and dependencies. |
| Original Streamlit UI | `scripts/run_local.py --legacy` -> `app/drift_communities_entry.py` -> `drift_communities.app` | Explicitly supported alternative interface. Keep, including `.streamlit/config.toml`, Streamlit, and Plotly dependencies. |
| Modular graph pipeline | `python -m provider_graph.cli` with `pipelines/ecs_build` on `PYTHONPATH`; tests import its features, Neo4j payloads, and similarity modules | Keep FAISS, Louvain, feature generation, and graph writes. This is batch engineering code, not web request code. |
| AWS Glue jobs | Managed Glue/PySpark job scripts under `pipelines/glue/jobs` | External job entry points. No local imports are expected; keep. |
| Parquet loader | `scripts/seed_neo4j.py`, documented in README | Explicit data-loading utility; keep. It is not an application startup task. |
| Architecture and data-model diagrams | `docs/*.svg`, `docs/*.drawio` | Portfolio and design artifacts; keep. Lack of a runtime import does not make a diagram unused. |
| Extraction report and provenance manifest | README provenance links | Historical audit records; keep unchanged. |
| `.env`, virtual environments, caches, local runtime files, and built frontend | Ignored local files | Excluded from Git. Do not delete or publish local configuration/data as part of source cleanup. |

## Follow-up candidates requiring a separate decision

| Candidate | Why it merits review | Work needed before removal or replacement |
| --- | --- | --- |
| `pipelines/ecs_build/build_provider_similarity_edges.py` | Older monolithic graph-builder entry point overlaps the modular `provider_graph/` implementation. It is still independently executable and could be referenced by an original ECS task definition outside this repo. | Compare configuration defaults, feature construction, graph payloads, and results on the same synthetic inputs. Establish a supported CLI and migration path before deleting it. |
| Streamlit interface | Overlaps React's provider review workflow but remains documented and runnable. | Decide whether to continue supporting it. Removing it requires updating the launcher, docs, runtime dependency graph, and tests together. |
| Python dependency separation | The API imports shared modules that still use Streamlit caching and Plotly. The pipeline also inherits the runtime requirements. | Trace shared dependencies before splitting API, legacy UI, and batch environments. Do not remove Streamlit or Plotly simply because the current browser UI uses React. |
| Remaining dependency list | Some packages may be needed only indirectly or by historical batch paths. | Validate in fresh environments and exercise the retained entry points before reducing the list further. No dependency upgrades in this pass. |

## Validation

Before and after cleanup: **45 Python tests passed** and the React production build passed. After cleanup, `pip check` reported no broken requirements; `git diff --check` passed; all 38 remaining Python files compiled. The retained API, Streamlit, OpenAI, Bedrock, and modular pipeline CLI imported successfully with the removed click-event package made unavailable and database/model client creation blocked. FAISS emitted three existing upstream SWIG deprecation warnings. The installed environment was checked in place; a fresh dependency installation and full Docker rebuild were not performed.

Tests use synthetic/mocked data, including native FAISS, evidence/query helpers, Neo4j payloads, OpenAI request/response handling, and API behavior. They do not execute AWS Glue jobs, a full CMS ingestion, or a live model request. No database or cloud resources need to be changed for this cleanup.
