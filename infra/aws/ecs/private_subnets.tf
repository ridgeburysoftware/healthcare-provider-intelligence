# Private subnets (no public IPs)
resource "aws_subnet" "private_a" {
  vpc_id                  = aws_vpc.vpc.id
  cidr_block              = "10.50.11.0/24"
  availability_zone       = data.aws_availability_zones.az.names[0]
  map_public_ip_on_launch = false
  tags                    = { Name = "${local.app_name}-private-a" }
}

resource "aws_subnet" "private_b" {
  vpc_id                  = aws_vpc.vpc.id
  cidr_block              = "10.50.12.0/24"
  availability_zone       = data.aws_availability_zones.az.names[1]
  map_public_ip_on_launch = false
  tags                    = { Name = "${local.app_name}-private-b" }
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.vpc.id
  tags   = { Name = "${local.app_name}-private-rt" }
}

resource "aws_route_table_association" "private_a" {
  subnet_id      = aws_subnet.private_a.id
  route_table_id = aws_route_table.private.id
}

resource "aws_route_table_association" "private_b" {
  subnet_id      = aws_subnet.private_b.id
  route_table_id = aws_route_table.private.id
}
