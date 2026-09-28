resource "aws_db_subnet_group" "zephyrwerk_rds_subnet_group" {
  name       = var.rds_subnet_group
  subnet_ids = aws_subnet.private[*].id
  tags = {
    Name        = var.rds_subnet_group
    Environment = "dev"
  }
}

resource "random_password" "zephyrwerk_rds_password" {
  length           = 32
  special          = false
}

resource "aws_secretsmanager_secret" "zephyrwerk_rds_secret" {
  name = "zephyrwerk/rds/credentials"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "zephyrwerk_rds_secret_version" {
  secret_id     = aws_secretsmanager_secret.zephyrwerk_rds_secret.id
  secret_string = jsonencode({
    username = var.rds_username
    password = random_password.zephyrwerk_rds_password.result
  })
}

resource "aws_db_instance" "zephyrwerk_rds" {
  identifier              = "zephyrwerk-rds-prod"
  engine                  = "postgres"
  engine_version          = "16"
  instance_class          = "db.t3.micro"
  allocated_storage       = 20
  storage_type            = "gp3"
  db_name                 = "zephyrwerk"
  db_subnet_group_name    = aws_db_subnet_group.zephyrwerk_rds_subnet_group.name
  vpc_security_group_ids  = [aws_security_group.zephyrwerk_rds_sg.id]
  username                = var.rds_username
  password                = random_password.zephyrwerk_rds_password.result
  skip_final_snapshot     = true
  publicly_accessible     = false
  multi_az                = false
  auto_minor_version_upgrade = true
  backup_retention_period = 1
  deletion_protection     = false
  apply_immediately       = true

  tags = {
    Name        = "zephyrwerk-rds"
    Environment = "dev"
  }
}