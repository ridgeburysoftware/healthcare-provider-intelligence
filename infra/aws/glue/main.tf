terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.71"
    }
  }
}

provider "aws" {
  region = var.region
}

data "aws_iam_policy_document" "glue_assume" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "glue_role" {
  name               = "AWSGlueServiceRole-demo"
  assume_role_policy = data.aws_iam_policy_document.glue_assume.json
}

resource "aws_iam_role_policy_attachment" "glue_managed" {
  role       = aws_iam_role.glue_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

# Bucket + prefixes you actually touch
resource "aws_iam_role_policy" "glue_s3_access" {
  name = "glue-s3-access"
  role = aws_iam_role.glue_role.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      # list bucket (needed for crawling)
      {
        Sid      = "ListBucket",
        Effect   = "Allow",
        Action   = ["s3:ListBucket"],
        Resource = "arn:aws:s3:::${var.artifacts_bucket}",
        Condition = {
          StringLike = {
            "s3:prefix" = [
              "${var.cms_raw_prefix}*",
              "communities/*",
              "${var.athena_results_prefix}*",
            ]
          }
        }
      },

      # read raw + derived + vectors
      {
        Sid    = "ReadObjects",
        Effect = "Allow",
        Action = ["s3:GetObject"],
        Resource = [
          "arn:aws:s3:::${var.artifacts_bucket}/${var.cms_raw_prefix}*",
          "arn:aws:s3:::${var.artifacts_bucket}/communities/*",
        ]
      },

      # write derived outputs + athena results (jobs + crawler updates can write)
      {
        Sid    = "WriteObjects",
        Effect = "Allow",
        Action = [
          "s3:PutObject",
          "s3:AbortMultipartUpload",
          "s3:ListBucketMultipartUploads",
          "s3:ListMultipartUploadParts"
        ],
        Resource = [
          "arn:aws:s3:::${var.artifacts_bucket}/communities/*",
          "arn:aws:s3:::${var.artifacts_bucket}/${var.athena_results_prefix}*",
        ]
      }
    ]
  })
}
resource "aws_glue_crawler" "cms_nppes_raw" {
  name          = "cms-nppes-raw"
  role          = aws_iam_role.glue_role.arn
  database_name = aws_glue_catalog_database.cms_raw.name

  s3_target {
    path = "${local.raw_s3}nppes/"
  }

  table_prefix = "" # keeps table name clean
  configuration = jsonencode({
    Version              = 1.0,
    CreatePartitionIndex = true
  })

  schema_change_policy {
    update_behavior = "UPDATE_IN_DATABASE"
    delete_behavior = "DEPRECATE_IN_DATABASE"
  }
}

resource "aws_glue_crawler" "cms_partb_raw" {
  name          = "cms-partb-raw"
  role          = aws_iam_role.glue_role.arn
  database_name = aws_glue_catalog_database.cms_raw.name

  s3_target { path = "${local.raw_s3}partb/" }

  configuration = jsonencode({ Version = 1.0, CreatePartitionIndex = true })

  schema_change_policy {
    update_behavior = "UPDATE_IN_DATABASE"
    delete_behavior = "DEPRECATE_IN_DATABASE"
  }
}

resource "aws_glue_crawler" "cms_partd_raw" {
  name          = "cms-partd-raw"
  role          = aws_iam_role.glue_role.arn
  database_name = aws_glue_catalog_database.cms_raw.name

  s3_target { path = "${local.raw_s3}partd/" }

  configuration = jsonencode({ Version = 1.0, CreatePartitionIndex = true })

  schema_change_policy {
    update_behavior = "UPDATE_IN_DATABASE"
    delete_behavior = "DEPRECATE_IN_DATABASE"
  }
}
resource "aws_glue_crawler" "cms_derived" {
  name          = "cms-derived"
  role          = aws_iam_role.glue_role.arn
  database_name = aws_glue_catalog_database.cms_derived.name

  # This is what you used: features/
  s3_target {
    path = local.derived_s3
  }

  # Optional: also crawl vectors outputs into same DB
  # s3_target { path = local.vectors_s3 }

  configuration = jsonencode({
    Version              = 1.0,
    CreatePartitionIndex = true
  })

  schema_change_policy {
    update_behavior = "UPDATE_IN_DATABASE"
    delete_behavior = "DEPRECATE_IN_DATABASE"
  }
}
resource "aws_athena_workgroup" "primary_demo" {
  name = "primary-demo"

  configuration {
    enforce_workgroup_configuration = true

    result_configuration {
      output_location = "s3://${var.artifacts_bucket}/${var.athena_results_prefix}"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}
locals {
  glue_temp_dir = "s3://aws-glue-assets-${data.aws_caller_identity.current.account_id}-${var.region}/temporary/"
}

data "aws_caller_identity" "current" {}

resource "aws_glue_job" "build_provider_features" {
  name     = "build_provider_features"
  role_arn = aws_iam_role.glue_role.arn

  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = 10

  command {
    name            = "glueetl"
    python_version  = "3"
    script_location = "s3://${var.artifacts_bucket}/glue/scripts/build_provider_features.py"
  }

  default_arguments = {
    "--TempDir"                      = local.glue_temp_dir
    "--job-language"                 = "python"
    "--enable-metrics"               = "true"
    "--enable-spark-ui"              = "true"
    "--enable-job-insights"          = "true"
    "--enable-observability-metrics" = "true"
    "--enable-glue-datacatalog"      = "true"

    # your job params (example)
    "--year"   = "2023"
    "--out_s3" = "s3://${var.artifacts_bucket}/communities/runs/${var.run_id}/features/"
  }
}

resource "aws_glue_job" "build_provider_vectors" {
  name     = "build_provider_vectors"
  role_arn = aws_iam_role.glue_role.arn

  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = 10

  command {
    name            = "glueetl"
    python_version  = "3"
    script_location = "s3://${var.artifacts_bucket}/glue/scripts/build_provider_vectors.py"
  }

  default_arguments = {
    "--TempDir"                      = local.glue_temp_dir
    "--job-language"                 = "python"
    "--enable-metrics"               = "true"
    "--enable-spark-ui"              = "true"
    "--enable-job-insights"          = "true"
    "--enable-observability-metrics" = "true"
    "--enable-glue-datacatalog"      = "true"
    "--job-bookmark-option"          = "job-bookmark-disable"

    # REQUIRED by your script
    "--hcpcs_s3" = "${local.derived_s3}provider_hcpcs/"
    "--drugs_s3" = "${local.derived_s3}provider_drugs/"
    "--out_s3"   = local.vectors_s3
    "--year"     = "2023"

    # Optional (you used these)
    "--unified_s3"      = "${local.derived_s3}provider_unified/"
    "--include_scalars" = "1"
    "--scalar_cols"     = "allowed_per_service,cost_per_claim"
    "--min_value"       = "1e-8"
    "--max_dim"         = "200000"
  }
}
resource "aws_glue_job" "normalize_provider_vectors" {
  name     = "normalize_provider_vectors"
  role_arn = aws_iam_role.glue_role.arn

  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = 10

  command {
    name            = "glueetl"
    python_version  = "3"
    script_location = "s3://${var.artifacts_bucket}/glue/scripts/normalize_provider_vectors.py"
  }

  default_arguments = {
    "--TempDir"                      = local.glue_temp_dir
    "--job-language"                 = "python"
    "--enable-metrics"               = "true"
    "--enable-spark-ui"              = "true"
    "--enable-job-insights"          = "true"
    "--enable-observability-metrics" = "true"
    "--enable-glue-datacatalog"      = "true"
    "--job-bookmark-option"          = "job-bookmark-disable"

    "--in_s3"  = "${local.vectors_s3}vectors_sparse/"
    "--out_s3" = local.vectors_s3
    "--year"   = "2023"
    "--eps"    = "1e-12"
  }
}

resource "aws_glue_crawler" "cms_vectors" {
  name          = "cms-vectors"
  role          = aws_iam_role.glue_role.arn
  database_name = aws_glue_catalog_database.cms_derived.name

  s3_target {
    path = local.vectors_s3
  }

  configuration = jsonencode({
    Version              = 1.0,
    CreatePartitionIndex = true
  })

  schema_change_policy {
    update_behavior = "UPDATE_IN_DATABASE"
    delete_behavior = "DEPRECATE_IN_DATABASE"
  }
}
