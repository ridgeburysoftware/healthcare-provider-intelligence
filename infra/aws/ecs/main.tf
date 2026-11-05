terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

# -----------------------------
# Inputs
# -----------------------------
locals {
  app_name       = "healthcare-demo-console"
  image_uri      = var.app_image_uri
  container_port = 8501
}

# -----------------------------
# Networking
# -----------------------------
data "aws_availability_zones" "az" {
  state = "available"
}

# The retained Neo4j stack accepts a separately supplied VPC.
data "aws_vpc" "neo4j_network" {
  id = var.vpc_id
}

resource "aws_vpc" "vpc" {
  cidr_block           = "10.50.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = { Name = "${local.app_name}-vpc" }
}

# Application resources use explicit security groups, not this VPC default group.
resource "aws_default_security_group" "default" {
  vpc_id  = aws_vpc.vpc.id
  ingress = []
  egress  = []
}

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.vpc.id
  tags   = { Name = "${local.app_name}-igw" }
}

resource "aws_subnet" "public_a" {
  vpc_id                  = aws_vpc.vpc.id
  cidr_block              = "10.50.1.0/24"
  availability_zone       = data.aws_availability_zones.az.names[0]
  map_public_ip_on_launch = false
  tags                    = { Name = "${local.app_name}-public-a" }
}

resource "aws_subnet" "public_b" {
  vpc_id                  = aws_vpc.vpc.id
  cidr_block              = "10.50.2.0/24"
  availability_zone       = data.aws_availability_zones.az.names[1]
  map_public_ip_on_launch = false
  tags                    = { Name = "${local.app_name}-public-b" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.vpc.id
  tags   = { Name = "${local.app_name}-public-rt" }
}

resource "aws_route" "public_default" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.igw.id
}

resource "aws_route_table_association" "public_a" {
  subnet_id      = aws_subnet.public_a.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "public_b" {
  subnet_id      = aws_subnet.public_b.id
  route_table_id = aws_route_table.public.id
}

# -----------------------------
# Security groups
# -----------------------------
resource "aws_security_group" "alb_sg" {
  name        = "${local.app_name}-alb-sg"
  description = "Public application load balancer"
  vpc_id      = aws_vpc.vpc.id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Forward requests to Streamlit within this VPC"
    from_port   = local.container_port
    to_port     = local.container_port
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.vpc.cidr_block]
  }
}

resource "aws_security_group" "task_sg" {
  name        = "${local.app_name}-task-sg"
  description = "Application tasks reachable only from the load balancer"
  vpc_id      = aws_vpc.vpc.id

  ingress {
    description     = "Streamlit from ALB"
    from_port       = local.container_port
    to_port         = local.container_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb_sg.id]
  }

  egress {
    description = "HTTPS for AWS endpoints and model invocation"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Bolt to the separately supplied Neo4j VPC"
    from_port   = 7687
    to_port     = 7687
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.neo4j_network.cidr_block]
  }
}

# -----------------------------
# ALB
# -----------------------------
resource "aws_lb" "alb" {
  name                       = "${local.app_name}-alb"
  load_balancer_type         = "application"
  security_groups            = [aws_security_group.alb_sg.id]
  subnets                    = [aws_subnet.public_a.id, aws_subnet.public_b.id]
  drop_invalid_header_fields = true
  enable_deletion_protection = true
}

resource "aws_lb_target_group" "tg" {
  name        = "${local.app_name}-tg"
  port        = local.container_port
  protocol    = "HTTP"
  vpc_id      = aws_vpc.vpc.id
  target_type = "ip"

  # Streamlit health endpoint
  health_check {
    protocol            = "HTTP"
    port                = "traffic-port"
    path                = "/apps/"
    matcher             = "200-399"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.alb.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.tg.arn
  }
}

# -----------------------------
# ECS (cluster, roles, task, service)
# -----------------------------
resource "aws_ecs_cluster" "cluster" {
  name = "${local.app_name}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_cloudwatch_log_group" "logs" {
  name              = "/ecs/${local.app_name}"
  retention_in_days = 365
}

data "aws_iam_policy_document" "task_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "task_execution_role" {
  name               = "${local.app_name}-task-exec"
  assume_role_policy = data.aws_iam_policy_document.task_assume.json
}

resource "aws_iam_role_policy_attachment" "task_exec_attach" {
  role       = aws_iam_role.task_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "task_exec_secret_access" {
  role = aws_iam_role.task_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Sid      = "ReadNeo4jAuthSecret",
        Effect   = "Allow",
        Action   = ["secretsmanager:GetSecretValue"],
        Resource = [var.neo4j_auth_secret_arn]
      }
    ]
  })
}

resource "aws_ecs_task_definition" "task" {
  family                   = local.app_name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "1024"
  memory                   = "2048"
  execution_role_arn       = aws_iam_role.task_execution_role.arn
  task_role_arn            = aws_iam_role.task_role.arn
  container_definitions = jsonencode([
    {
      name      = local.app_name
      image     = local.image_uri
      essential = true

      portMappings = [
        {
          containerPort = local.container_port,
          hostPort      = local.container_port,
          protocol      = "tcp"
        }
      ]


      command = [
        "streamlit", "run", "app/drift_communities_entry.py",
        "--server.port=8501",
        "--server.address=0.0.0.0",
        "--server.baseUrlPath=apps",
        "--server.enableCORS=false",
        "--server.enableXsrfProtection=false",
        "--server.enableWebsocketCompression=false"
      ]

      environment = [
        { name = "NEO4J_URI", value = "bolt://neo4j.healthcare.local:7687" },
        { name = "NEO4J_USER", value = "neo4j" },
        { name = "AWS_REGION", value = var.region },
        { name = "BEDROCK_MODEL_ID", value = var.bedrock_model_id }

      ]
      secrets = [
        { name = "NEO4J_AUTH", valueFrom = "${var.neo4j_auth_secret_arn}:NEO4J_AUTH::" }
      ]

      logConfiguration = {
        logDriver = "awslogs",
        options = {
          awslogs-group         = aws_cloudwatch_log_group.logs.name,
          awslogs-region        = var.region,
          awslogs-stream-prefix = "app"
        }
      }
    }
  ])

}

resource "aws_ecs_service" "svc" {
  name            = "${local.app_name}-svc"
  cluster         = aws_ecs_cluster.cluster.id
  task_definition = aws_ecs_task_definition.task.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = [aws_subnet.public_a.id, aws_subnet.public_b.id]
    security_groups  = [aws_security_group.task_sg.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.tg.arn
    container_name   = local.app_name
    container_port   = local.container_port
  }

  depends_on = [aws_lb_listener.http]
}

output "alb_url" {
  value = "http://${aws_lb.alb.dns_name}"
}

# Task role
resource "aws_iam_role" "task_role" {
  name               = "${local.app_name}-task-role"
  assume_role_policy = data.aws_iam_policy_document.task_assume.json
}

# Bedrock invoke policy
data "aws_iam_policy_document" "bedrock_invoke" {
  statement {
    sid    = "InvokeBedrockModels"
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream"
    ]
    resources = ["*"]
  }

  statement {
    sid    = "MarketplaceModelSubscriptionRead"
    effect = "Allow"
    actions = [
      "aws-marketplace:ViewSubscriptions",
      "aws-marketplace:Subscribe"
    ]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "bedrock_invoke" {
  name   = "${local.app_name}-bedrock-invoke"
  policy = data.aws_iam_policy_document.bedrock_invoke.json
}

resource "aws_iam_role_policy_attachment" "task_role_bedrock" {
  role       = aws_iam_role.task_role.name
  policy_arn = aws_iam_policy.bedrock_invoke.arn
}
