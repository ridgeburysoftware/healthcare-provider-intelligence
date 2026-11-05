# Original AWS infrastructure

These two Terraform roots preserve the Provider Intelligence project's original AWS implementation. They are engineering reference configurations, not the deployment configuration for the current React/FastAPI demonstration.

| Root | Original resources |
| --- | --- |
| [`ecs/`](ecs/) | Application Load Balancer, ECS/Fargate application and Neo4j tasks, VPC/subnets, private service discovery, EFS storage, VPC endpoints, CloudWatch logs, IAM, and a loader task definition. |
| [`glue/`](glue/) | CMS Glue catalogs/crawlers, feature/vector transformation jobs, IAM, and an Athena workgroup. |

The original source commit and file hashes are recorded in [SOURCE-PROVENANCE.json](SOURCE-PROVENANCE.json). The application extraction report is a historical record; this infrastructure was added afterward.

## Publication changes

Private ECR image locations, the account-specific Bedrock inference-profile ARN, and the original S3 bucket were replaced by input variables. Region references now use the region input. The initial publication retained resource definitions, historical networking inputs, IAM policies, workload commands, and sizing. Subsequent safe security hardening is documented below. An obsolete comment describing Neo4j storage as ephemeral was corrected to match its existing EFS mount.

There are no AWS credentials, state files, plans, private tfvars, database dumps, or provider binaries in this directory. The checked-in lockfiles select the original AWS provider 5.100.0. `.tfvars.example` files contain placeholders; real `.tfvars` files remain ignored.

## Security hardening after publication

The security review added EFS encryption at rest, constrained security-group egress, explicit default-group restrictions, subnet public-IP defaults, ALB header/deletion protection, Container Insights, longer CloudWatch retention, and Athena result encryption. Workload commands and application source remain unchanged. These templates still require deployment review; [23 deployment-specific Checkov findings remain open](../../docs/SECURITY-REVIEW.md).

The provenance file records the historical extraction source, not a claim that later hardened files are byte-identical to it. Dependency diagrams now reflect the current checked-in configuration. No AWS deployment was performed. Enabling EFS encryption can replace an existing unencrypted filesystem and requires a data migration review; review egress CIDRs and externally supplied VPC inputs before applying any changes.

## Local inspection and diagrams

Requires Terraform 1.5+ for configuration validation; the simplified resource diagram command requires Terraform 1.7+. Validation for this extraction used Terraform 1.14.3. Graphviz `dot` is needed only to render diagrams.

From the repository root:

```sh
terraform -chdir=infra/aws/ecs init -backend=false -input=false -lockfile=readonly
terraform -chdir=infra/aws/ecs validate
terraform -chdir=infra/aws/glue init -backend=false -input=false -lockfile=readonly
terraform -chdir=infra/aws/glue validate
terraform fmt -check -recursive infra/aws
python scripts/terraform_diagrams.py
```

Initialization downloads provider plugins from the Terraform registry. These commands do not run a plan/apply, read deployment state, or require an AWS account connection. The diagram script runs `terraform graph` against each initialized root and renders its output using Graphviz; it does not initialize Terraform, load a plan, or deploy infrastructure. Use `--dot /path/to/dot` if Graphviz is not on `PATH`.

See [the diagrams](../../docs/terraform/README.md). They show resource dependencies in configuration. They do not establish what is currently deployed in AWS, and their arrows are not application data-flow arrows.

## Prerequisites and historical limitations

Before considering an AWS deployment, review these retained assumptions:

- The application task launches the original Streamlit interface at `/apps/` on port 8501. Supply a compatible image with the source and dependencies. The root Dockerfile builds the current FastAPI application and is not a replacement for that historical image.
- The loader task refers to a separately prepared image with `/app/entrypoint.sh`. That loader image/source and its dump are not part of this extraction. The Neo4j image must also be supplied explicitly and reachable from the selected subnets.
- Application networking creates a VPC, public/private subnets, security groups, cluster, and execution role. Neo4j, EFS, and endpoints retain explicit networking/cluster/role inputs from the original staged setup. They are not automatically connected to those newly created resources; callers must reconcile the inputs and resource dependencies before a fresh deployment. Two unused historical security-group inputs remain pending a focused infrastructure cleanup.
- Secrets Manager must contain the supplied secret ARN with a JSON field named `NEO4J_AUTH` holding `user/password`. Terraform references the secret; its value is not included here.
- The S3 artifact bucket, CMS source files, uploaded Glue scripts, Glue temporary bucket, feature datasets, and any saved Neo4j dump must already exist. These roots do not create or populate those inputs.
- Glue's `build_provider_features.py` requires job-run arguments including `partb_s3`, `partd_s3`, `nppes_s3`, `topk_hcpcs`, and `topk_drugs` beyond the retained job defaults. Supply them when running the job; deployment alone does not execute or validate ingestion.
- The historical loader requests `neo4j/dumps/neo4j.dump`, while its read policy names `neo4j.dump`; its combined list/read policy and `bolt://neo4j:7687` endpoint also require deployment review. These historical inconsistencies were recorded rather than silently changing behavior during publication.
- The original application listener is HTTP and its Bedrock policy includes broad model/marketplace permissions. Review endpoint/TLS requirements and IAM permissions for the target environment before reuse.

No AWS plan, apply, live infrastructure validation, data ingestion, or model call was performed while publishing this source. Local validation does not certify a complete fresh deployment.

## Publication validation

Both roots passed `terraform validate` with zero errors and zero warnings, and `terraform fmt -check -recursive infra/aws` passed. Both SVG diagrams were regenerated from the current checked-in configuration. The original extraction had matching source hashes and dependency graphs; subsequent security hardening intentionally changes the current configuration graph. No AWS plan or apply was run.
