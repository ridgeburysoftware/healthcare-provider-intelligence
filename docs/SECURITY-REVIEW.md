# Security automation and review

Reviewed 2026-11-05. This review covers repository source and dependency declarations. It is not a penetration test or an audit of the running VPS/AWS account. No AWS plan/apply, production redeployment, database access, or model request is part of this change.

## Automated checks

| Check | Configuration | Result and scope |
| --- | --- | --- |
| Gitleaks 8.30.1 | [Workflow](../.github/workflows/gitleaks.yml), [rules](../.gitleaks.toml) | Full fetched Git history, including pull-request commits. Findings are fully redacted. The reviewed EFS creation identifier is the only exact-line false-positive allowance. |
| Checkov 3.4.3 | [Workflow](../.github/workflows/checkov.yml) | Terraform, Dockerfile and GitHub Actions. Blocking failures, no baseline, no skipped policies and no soft-fail. SARIF is uploaded to GitHub code scanning on trusted runs, including failed scans. |
| CodeQL | GitHub-managed default setup | Python and JavaScript/TypeScript; push/PR analysis and GitHub's weekly schedule. The existing successful managed setup is retained; there is no duplicate CodeQL workflow. |
| Dependabot | [Configuration](../.github/dependabot.yml) | Weekly updates for root Python manifests, `/frontend` npm, root Dockerfile, GitHub Actions, and both AWS Terraform roots. Existing dependency alerts and security updates remain enabled. Updates create reviewable PRs; there is no automatic merge. |

Gitleaks and Checkov run on pushes to `main`, pull requests, weekly schedules and manual dispatch. README badges link to the actual Actions workflows, not manually maintained success labels. Checkov's badge remains failing while the AWS gaps below remain unresolved.

Workflow permissions default to `contents: read`. Only the Checkov job requests `security-events: write` for SARIF publication. It does not request content, PR, issue, deployment or OIDC write access. Fork and Dependabot PRs still run the scanner, but skip SARIF publication with their restricted tokens. Neither scanner receives application credentials or cloud keys, and checkout does not persist Git credentials. The Gitleaks CLI archive has a fixed SHA-256; Actions use full commit SHAs; Checkov uses a fixed image digest. Its scan container has no network, a read-only filesystem/source mount, a non-root user, and no Linux capabilities. No privileged pull-request trigger or repository scripts are executed by the scanners.

Checkov scans only the declared infrastructure formats, so secret scanning is handled by Gitleaks and GitHub's existing secret scanning. Checkov does not scan a live AWS account. Changes to the pinned Gitleaks release/checksum or Checkov version/digest require review; Dependabot maintains supported Actions, image and provider references in its configured manifests.

## Findings fixed

The initial Checkov scan found 48 failed resource/check pairs. Safe source hardening resolved 25; the current scan has **341 passing checks, 23 failed Terraform checks, zero skipped checks and zero parsing errors**. Dockerfile checks pass (92); GitHub Actions checks pass (44); Terraform has 205 passing checks and the 23 findings below.

- Enable EFS encryption at rest using the AWS-managed default key. A deployment-specific customer-managed key remains outstanding.
- Restrict ALB egress to the application port inside its VPC; restrict application/Neo4j egress to HTTPS, Bolt and NFS destinations. Remove unnecessary outbound permissions from EFS/endpoint security groups; stateful response traffic remains allowed.
- Deny traffic through the newly created VPC's unused default security group. Disable automatic subnet public-IP assignment; explicitly configured ECS public IPs remain a separate unresolved finding.
- Add security-group/rule descriptions, ALB invalid-header rejection and deletion protection, ECS Container Insights, and 365-day application/Neo4j CloudWatch retention.
- Enforce SSE-S3 encryption for Athena results.
- Add a Docker image health probe against the static web entrypoint without querying Neo4j or calling AI.

The EFS `creation_token` declaration is an idempotency/resource creation identifier, not authentication material. Gitleaks' generic API-key rule flagged it in the original Terraform commit. The allowlist requires both this exact file and complete declaration; it does not disable the rule, ignore Terraform files, or conceal an actual credential. No secret rotation or Git history rewrite was needed.

The dependency review found vulnerable Python versions even though GitHub initially reported no open dependency alerts. These pins were updated:

| Dependency | Before | Reviewed update | Reason |
| --- | --- | --- | --- |
| Streamlit | 1.53.1 | 1.67.0 | Fix Windows SSRF/NTLM exposure and allow the fixed Pillow 13 dependency. 1.54.0 through 1.66.0 still require Pillow below 13. |
| Pillow (transitive) | 12.3.0 resolved | 13.0.0 explicitly pinned | Fix image-codec memory-safety and other advisories. |
| PyArrow | 23.0.0 | 23.0.1 | Fix the bundled Arrow C++ IPC reader advisory; the application does not enable the affected C++ pre-buffering API. |
| pytest (development only) | 9.0.2 | 9.0.3 | Fix insecure temporary-directory handling. |

Sources: [Streamlit advisory](https://github.com/advisories/GHSA-7p48-42j8-8846), [Pillow 13 security release](https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html), [Arrow 23.0.1](https://arrow.apache.org/blog/2026/02/16/23.0.1-release/), [pytest 9.0.3](https://github.com/pytest-dev/pytest/releases/tag/9.0.3).

No application source, API routes, analytics calculations, AI prompts, UI components or Compose configuration changed. Dependencies are security updates and require normal regression verification. These source changes do not update the already-running VPS containers.

## Local validation results
+
+- Python audit of the complete runtime/pipeline/development requirement set: **82 resolved packages, zero known vulnerability records** after the updates.
+- Frontend `npm audit`: **zero vulnerabilities**.
+- Existing synthetic/mocked application tests: **45 passed** (three existing FAISS/SWIG deprecation warnings); no live database/model calls.
+- `pip check`, frontend production build, actionlint and both Terraform validations passed; Terraform reported zero errors/warnings. Formatting passed and dependency diagrams were regenerated.
+- Checkov's Docker/Actions checks passed; its Terraform findings below intentionally remain blocking.
+
+## Remaining AWS deployment-specific findings

These are real unresolved findings in retained AWS reference Terraform. They are not dismissed or suppressed. The current demonstration is hosted independently of AWS; these findings do not describe the VPS's live TLS, database or network configuration.

| Area | Failed checks | Resource/check pairs | Required deployment decision |
| --- | --- | --- | --- |
| HTTPS and transport | `CKV_AWS_260`, `CKV_AWS_2`, `CKV_AWS_103`, `CKV_AWS_378`, `CKV2_AWS_20` | 5 | Supply an ACM certificate/DNS and a TLS policy, redirect/remove public HTTP, and decide how to encrypt ALB-to-Streamlit traffic. The historical application speaks HTTP and needs a compatible TLS endpoint/proxy for an HTTPS target group. |
| Customer-managed encryption | `CKV_AWS_184`, `CKV_AWS_158` | 3 | Select KMS keys and key policies for EFS and both CloudWatch groups, including service/role permissions. EFS encryption at rest is already enabled with the default key. |
| Glue encryption configuration | `CKV_AWS_195` | 8 | Associate a validated Glue security configuration with the five crawlers and three jobs, including the intended S3, log and bookmark encryption/key permissions. |
| Audit logging | `CKV_AWS_91`, `CKV2_AWS_11` | 2 | Supply an ALB access-log bucket/policy and a VPC flow-log destination, retention and writer role. |
| Bedrock IAM | `CKV_AWS_356` | 1 | Scope runtime invocation to the intended model/inference-profile ARNs and move marketplace/subscription permissions to the provisioning identity. The model choice is an external input. |
| Application public IP | `CKV_AWS_333` | 1 | Reconcile the historical VPC inputs and move app tasks to working private networking with required egress/endpoints. Disabling the public IP alone would break the retained outbound access path. |
| External loader image | `CKV_AWS_336` | 1 | Audit the separately supplied loader image's writable paths before enforcing a read-only root filesystem. The image/source is not in this repository. |
| Availability zones | `CKV_AWS_394` | 1 | Choose and pin suitable zone identities for the target region/account. |
| WAF | `CKV2_AWS_28` | 1 | Choose a Web ACL, rules and operational policy for the public ALB. |

**Not all security checks pass.** Checkov correctly exits nonzero for these 23 pairs. Do not add a blanket skip, soft-fail or baseline merely to turn the badge green.

Do not apply these historical templates without the infrastructure deployment review already described in [infra/aws/README.md](../infra/aws/README.md). Enabling EFS encryption can replace an existing unencrypted filesystem; preserve/migrate data first. The stricter egress uses the supplied VPC's primary CIDR, so review secondary CIDRs/custom DNS and the historical cross-VPC inputs before deployment. ALB deletion protection must be deliberately disabled before teardown. Log retention and Container Insights affect operational storage/costs if applied.

## Reproducing scans

Install the pinned Gitleaks CLI from its official release and verify the archive checksum before use:

```sh
gitleaks git . --log-opts="--all" --redact=100 --no-banner
```

For Checkov, use the read-only/offline Docker command in [the workflow](../.github/workflows/checkov.yml). Run it against a clean source checkout/export, excluding private `.env`, generated analysis artifacts and datasets. No AWS credentials or state are required. The workflow generates SARIF even when legitimate findings cause the scan to fail.

Dependency review commands (use an isolated audit environment):

```sh
python -m pip_audit -r requirements-dev.txt
npm audit --prefix frontend
```

Application regression checks:

```sh
python -m pytest
npm run build --prefix frontend
terraform -chdir=infra/aws/ecs validate
terraform -chdir=infra/aws/glue validate
terraform fmt -check -recursive infra/aws
```

Terraform validation and diagrams do not execute a plan/apply. GitHub-managed CodeQL results and the security workflows' real run results are available from the README badges. Scanner/advisory results are time-specific and should be reviewed on subsequent runs.
