resource "aws_db_subnet_group" "zephyrwerk_rds_subnet_group" {
  name       = var.rds_subnet_group
  subnet_ids = aws_subnet.private[*].id
  tags = {
    Name        = var.rds_subnet_group
    Environment = "dev"
  }
}