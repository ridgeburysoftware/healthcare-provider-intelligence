variable "region" {
  type    = string
  default = "us-east-1"
}

variable "artifacts_bucket" {
  type        = string
  description = "Existing S3 bucket for CMS inputs, Glue scripts, and derived artifacts."
}

variable "athena_results_prefix" {
  type    = string
  default = "athena-results/"
}

variable "cms_raw_prefix" {
  type    = string
  default = "cms/raw/"
}

variable "run_id" {
  type    = string
  default = "RUN_2023_01"
}

locals {
  raw_s3     = "s3://${var.artifacts_bucket}/${var.cms_raw_prefix}"
  derived_s3 = "s3://${var.artifacts_bucket}/communities/runs/${var.run_id}/features/"
  vectors_s3 = "s3://${var.artifacts_bucket}/communities/runs/${var.run_id}/vectors/"
}
