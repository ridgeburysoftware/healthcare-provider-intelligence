# efs.tf
resource "aws_security_group" "efs_sg" {
  name        = "healthcare-efs-sg"
  description = "Allow NFS from Neo4j tasks"
  vpc_id      = var.vpc_id

  ingress {
    description     = "NFS from Neo4j"
    from_port       = 2049
    to_port         = 2049
    protocol        = "tcp"
    security_groups = [aws_security_group.neo4j_sg.id]
  }

  # No outbound connections: security groups allow replies to permitted NFS requests.
  egress = []
}

resource "aws_efs_file_system" "neo4j" {
  creation_token = "healthcare-neo4j-efs"
  encrypted      = true

  lifecycle_policy {
    transition_to_ia = "AFTER_30_DAYS"
  }

  tags = {
    Name = "healthcare-neo4j-efs"
  }
}

# One mount target per subnet (EFS requires this)
resource "aws_efs_mount_target" "neo4j" {
  for_each        = toset(var.private_subnet_ids)
  file_system_id  = aws_efs_file_system.neo4j.id
  subnet_id       = each.value
  security_groups = [aws_security_group.efs_sg.id]
}
