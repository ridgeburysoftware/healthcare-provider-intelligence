# vpce_sg.tf
resource "aws_security_group" "vpce_sg" {
  name        = "healthcare-vpce-sg"
  description = "Allow HTTPS from ECS tasks to interface endpoints"
  vpc_id      = var.vpc_id

  # no inline ingress rules here (we’ll add as separate rule resources)
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Allow HTTPS into the endpoint ENIs from the app task SG
resource "aws_security_group_rule" "vpce_ingress_from_app" {
  type                     = "ingress"
  security_group_id        = aws_security_group.vpce_sg.id
  from_port                = 443
  to_port                  = 443
  protocol                 = "tcp"
  source_security_group_id = var.app_task_sg_id
}

# Allow HTTPS into the endpoint ENIs from neo4j task SG (so neo4j can reach CloudWatch logs too)
resource "aws_security_group_rule" "vpce_ingress_from_neo4j" {
  type                     = "ingress"
  security_group_id        = aws_security_group.vpce_sg.id
  from_port                = 443
  to_port                  = 443
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.neo4j_sg.id
}
