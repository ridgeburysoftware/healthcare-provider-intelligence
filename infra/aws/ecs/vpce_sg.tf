# vpce_sg.tf
resource "aws_security_group" "vpce_sg" {
  name        = "healthcare-vpce-sg"
  description = "Allow HTTPS from ECS tasks to interface endpoints"
  vpc_id      = var.vpc_id

  # no inline ingress rules here (weâ€™ll add as separate rule resources)
  # Interface endpoints only answer permitted inbound requests; no outbound rule is needed.
  egress = []
}

# Allow HTTPS into the endpoint ENIs from the app task SG
resource "aws_security_group_rule" "vpce_ingress_from_app" {
  description              = "HTTPS from the configured application tasks"
  type                     = "ingress"
  security_group_id        = aws_security_group.vpce_sg.id
  from_port                = 443
  to_port                  = 443
  protocol                 = "tcp"
  source_security_group_id = var.app_task_sg_id
}

# Allow HTTPS into the endpoint ENIs from neo4j task SG (so neo4j can reach CloudWatch logs too)
resource "aws_security_group_rule" "vpce_ingress_from_neo4j" {
  description              = "HTTPS from Neo4j tasks"
  type                     = "ingress"
  security_group_id        = aws_security_group.vpce_sg.id
  from_port                = 443
  to_port                  = 443
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.neo4j_sg.id
}
