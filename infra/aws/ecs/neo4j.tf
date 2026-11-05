############################################
# Neo4j (ECS/Fargate) - same VPC/subnets
# Private-only. App tasks can reach Bolt.
############################################

locals {
  neo4j_name      = "neo4j"
  neo4j_http_port = 7474
  neo4j_bolt_port = 7687
}

# -------------
# Log group
# -------------
resource "aws_cloudwatch_log_group" "neo4j" {
  name              = "/ecs/healthcare-neo4j"
  retention_in_days = 365
}

# -------------
# SG: Neo4j
# Only allow inbound from your app task SG.
# -------------
resource "aws_security_group" "neo4j_sg" {
  name        = "healthcare-neo4j-sg"
  description = "Neo4j SG (allow from app tasks only)"
  vpc_id      = var.vpc_id

  egress {
    description = "HTTPS for registry and AWS endpoints"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "NFS to EFS mount targets within the supplied VPC"
    from_port   = 2049
    to_port     = 2049
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.neo4j_network.cidr_block]
  }
}

# App -> Neo4j Bolt
resource "aws_security_group_rule" "neo4j_ingress_bolt" {
  description              = "Bolt from the configured application task security group"
  type                     = "ingress"
  security_group_id        = aws_security_group.neo4j_sg.id
  from_port                = local.neo4j_bolt_port
  to_port                  = local.neo4j_bolt_port
  protocol                 = "tcp"
  source_security_group_id = var.app_task_sg_id
}

# (Optional internal) App -> Neo4j Browser
resource "aws_security_group_rule" "neo4j_ingress_http" {
  description              = "Internal Neo4j Browser from the configured application tasks"
  type                     = "ingress"
  security_group_id        = aws_security_group.neo4j_sg.id
  from_port                = local.neo4j_http_port
  to_port                  = local.neo4j_http_port
  protocol                 = "tcp"
  source_security_group_id = var.app_task_sg_id
}

# -------------
# Service discovery (Cloud Map)
# Gives you: bolt://neo4j.healthcare.local:7687
# -------------
resource "aws_service_discovery_private_dns_namespace" "healthcare" {
  name        = "healthcare.local"
  description = "Private DNS namespace for healthcare-demo-console ECS"
  vpc         = var.vpc_id
}

resource "aws_service_discovery_service" "neo4j" {
  name = local.neo4j_name

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.healthcare.id

    dns_records {
      type = "A"
      ttl  = 10
    }

    routing_policy = "MULTIVALUE"
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}

# -------------
# Task definition (Neo4j)
# Neo4j data is mounted from the EFS volume declared below.
# -------------
resource "aws_ecs_task_definition" "neo4j" {
  family                   = "healthcare-neo4j"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "1024"
  memory                   = "2048"
  execution_role_arn       = var.ecs_task_execution_role_arn

  volume {
    name = "neo4j-data"
    efs_volume_configuration {
      file_system_id     = aws_efs_file_system.neo4j.id
      transit_encryption = "ENABLED"
    }
  }

  container_definitions = jsonencode([
    {
      name  = "neo4j"
      image = var.neo4j_image_uri

      essential = true

      portMappings = [
        { containerPort = local.neo4j_http_port, hostPort = local.neo4j_http_port, protocol = "tcp" },
        { containerPort = local.neo4j_bolt_port, hostPort = local.neo4j_bolt_port, protocol = "tcp" }
      ]

      "mountPoints" : [
        { "sourceVolume" : "neo4j-data", "containerPath" : "/data", "readOnly" : false }
      ]


      environment = [
        # Keep memory sane on small Fargate
        { name = "NEO4J_server_memory_heap_initial__size", value = "512m" },
        { name = "NEO4J_server_memory_heap_max__size", value = "1024m" },
        { name = "NEO4J_server_memory_pagecache_size", value = "512m" }
      ]
      secrets = [
        # Neo4j expects this exact format: user/password
        { name = "NEO4J_AUTH", valueFrom = "${var.neo4j_auth_secret_arn}:NEO4J_AUTH::" }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-region        = var.region
          awslogs-group         = aws_cloudwatch_log_group.neo4j.name
          awslogs-stream-prefix = "neo4j"
        }
      }
    }
  ])
}

# -------------
# ECS Service (private subnets, no public IP)
# -------------
resource "aws_ecs_service" "neo4j" {
  name            = "healthcare-neo4j"
  cluster         = var.ecs_cluster_name
  task_definition = aws_ecs_task_definition.neo4j.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.neo4j_sg.id]
    assign_public_ip = false
  }

  service_registries {
    registry_arn = aws_service_discovery_service.neo4j.arn
  }
}
