resource "aws_ecs_task_definition" "neo4j_loader" {
  family                   = "neo4j-loader"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "1024" # bump a bit for python/FAISS
  memory                   = "2048"

  execution_role_arn = var.ecs_task_execution_role_arn
  task_role_arn      = aws_iam_role.ecs_task_role.arn

  volume {
    name = "neo4j_efs"
    efs_volume_configuration {
      file_system_id     = aws_efs_file_system.neo4j.id
      transit_encryption = "ENABLED"
    }
  }

  container_definitions = jsonencode([
    {
      name      = "neo4j-loader",
      image     = var.loader_image_uri,
      essential = true,

      # optional: if your image supports it; otherwise omit and rely on image ENTRYPOINT
      command = ["/app/entrypoint.sh"],

      environment = [
        # --- MODE switch ---
        { name = "MODE", value = "dump" },

        # --- dump mode ---
        { name = "S3_DUMP_URI", value = "s3://${var.artifacts_bucket}/neo4j/dumps/neo4j.dump" },
        { name = "NEO4J_DB_NAME", value = "neo4j" },

        # --- build_graph mode (used only if MODE=build_graph) ---
        { name = "RUN_ID", value = "RUN_2023_01" },
        { name = "YEAR", value = "2023" },

        { name = "DRUGS_S3", value = "s3://${var.artifacts_bucket}/communities/runs/RUN_2023_01/features/provider_drugs/" },
        { name = "HCPCS_S3", value = "s3://${var.artifacts_bucket}/communities/runs/RUN_2023_01/features/provider_hcpcs/" },
        { name = "UNIFIED_S3", value = "s3://${var.artifacts_bucket}/communities/runs/RUN_2023_01/features/provider_unified/" },

        # algo params (match UI expectations)
        { name = "TOP_D", value = "25" },
        { name = "TOP_B", value = "25" },
        { name = "TOP_K", value = "25" },
        { name = "SIM_THRESHOLD", value = "0.35" },

        # neo4j bolt endpoint inside VPC
        { name = "NEO4J_URI", value = "bolt://neo4j:7687" }, # adjust to your service DNS / private endpoint
        { name = "NEO4J_USER", value = "neo4j" },
        { name = "NEO4J_DB", value = "neo4j" },
      ],
      secrets = [
        { name = "NEO4J_AUTH", valueFrom = "${var.neo4j_auth_secret_arn}:NEO4J_AUTH::" }
      ],

      mountPoints = [
        { sourceVolume = "neo4j_efs", containerPath = "/data", readOnly = false }
      ],

      logConfiguration = {
        logDriver = "awslogs",
        options = {
          awslogs-region        = var.region,
          awslogs-group         = aws_cloudwatch_log_group.neo4j.name,
          awslogs-stream-prefix = "neo4j-loader"
        }
      }
    }
  ])
}


data "aws_iam_policy_document" "ecs_task_assume_role" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "ecs_task_role" {
  name               = "healthcare-ecs-task-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume_role.json
}

resource "aws_iam_role_policy" "neo4j_dump_read" {
  role = aws_iam_role.ecs_task_role.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Sid      = "ReadNeo4jDump",
        Effect   = "Allow",
        Action   = ["s3:GetObject"],
        Resource = "arn:aws:s3:::${var.artifacts_bucket}/neo4j.dump"
      }
    ]
  })
}

resource "aws_iam_role_policy" "communities_features_read" {
  role = aws_iam_role.ecs_task_role.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Sid : "ReadCommunitiesRunFeatures",
        Effect : "Allow",
        Action : ["s3:GetObject", "s3:ListBucket"],
        Resource : [
          "arn:aws:s3:::${var.artifacts_bucket}",
          "arn:aws:s3:::${var.artifacts_bucket}/communities/runs/*"
        ],
        Condition : {
          StringLike : {
            "s3:prefix" : [
              "communities/runs/*"
            ]
          }
        }
      }
    ]
  })
}
