# Terraform dependency diagrams

Generated from the historical AWS configurations under [`infra/aws`](../../infra/aws/README.md), with deployment-specific settings replaced by inputs and subsequent [safe security hardening](../SECURITY-REVIEW.md).

- [ECS/Fargate application infrastructure](infra-ecs.svg): 53 resource blocks and 5 data sources.
- [Glue data pipeline](infra-pipeline.svg): 14 resource blocks and 2 data sources.

SVG files remain readable when zoomed. The adjacent `.dot` files are the current `terraform graph` output. Presentation styling affects only fonts, colors, and spacing; it does not add or remove resources or edges.

Arrows point from a resource to its dependencies. These are configuration dependency graphs, not current AWS inventory or application data-flow diagrams. Existing S3 buckets and Bedrock services referenced through input values may not appear as standalone nodes. The Terraform roots are separate, so no cross-root dependencies are invented.

After initializing both roots with backend initialization disabled, regenerate from the repository root:

```sh
python scripts/terraform_diagrams.py
```

Use `--dot /path/to/dot` or `--terraform /path/to/terraform` for tools outside `PATH`. Terraform 1.7+ and Graphviz are required. Generation performs no plan or apply and uses no saved state or tfvars. The original marketing-site Terraform is outside this project's scope.
