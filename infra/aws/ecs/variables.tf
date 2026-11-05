variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "private_route_table_ids" { type = list(string) }
variable "app_task_sg_id" { type = string }
variable "alb_sg_id" { type = string }
variable "vpce_sg_id" { type = string }
variable "ecs_cluster_name" { type = string }
variable "ecs_task_execution_role_arn" { type = string }
variable "neo4j_auth_secret_arn" { type = string }

# Deployment-specific values from the original AWS environment are supplied by the caller.
variable "region" {
  description = "AWS region for this historical application stack."
  type        = string
  default     = "us-east-1"
}

variable "app_image_uri" {
  description = "Image containing the original Streamlit application and its dependencies."
  type        = string
}

variable "neo4j_image_uri" {
  description = "Neo4j image available to the target AWS deployment."
  type        = string
}

variable "loader_image_uri" {
  description = "Separately prepared historical dump-loader/graph-builder image."
  type        = string
}

variable "artifacts_bucket" {
  description = "Existing S3 bucket holding the Neo4j dump and community feature data."
  type        = string
}

variable "bedrock_model_id" {
  description = "Bedrock model or inference-profile identifier for the original AWS interface."
  type        = string
  default     = ""
}
