resource "aws_security_group" "zephyrwerk_pipeline_sg" {
  name        = var.pipeline_sg
  description = "Security group for Zephyrwerk pipeline"
  vpc_id      = aws_vpc.main.id
  tags = {
    Name        = var.pipeline_sg
    Environment = "dev"
  }
}

resource "aws_security_group" "zephyrwerk_api_sg" {
  name        = var.api_sg
  description = "Security group for Zephyrwerk API"
  vpc_id      = aws_vpc.main.id
  tags = {
    Name        = var.api_sg
    Environment = "dev"
  }
}

resource "aws_security_group" "zephyrwerk_dashboard_sg" {
  name = var.dashboard_sg
  description = "Security group for Zephyrwerk dashboard"
  vpc_id = aws_vpc.main.id
  tags = {
    Name = var.dashboard_sg
    Environment = "dev"
  }
}

resource "aws_security_group" "zephyrwerk_rds_sg" {
  name        = var.rds_sg
  description = "Security group for Zephyrwerk RDS"
  vpc_id      = aws_vpc.main.id
  tags = {
    Name        = var.rds_sg
    Environment = "dev"
  }
}


resource "aws_vpc_security_group_egress_rule" "zephyrwerk_api_sg_egress" {
  security_group_id = aws_security_group.zephyrwerk_api_sg.id
  ip_protocol          = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "zephyrwerk_pipeline_sg_egress" {
  security_group_id = aws_security_group.zephyrwerk_pipeline_sg.id
  ip_protocol          = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "zephyrwerk_dashboard_sg_egress" {
  security_group_id = aws_security_group.zephyrwerk_dashboard_sg.id
  ip_protocol = "-1"
  cidr_ipv4 = "0.0.0.0/0"
}


resource "aws_vpc_security_group_ingress_rule" "zephyrwerk_rds_from_api_sg_ingress" {
  security_group_id = aws_security_group.zephyrwerk_rds_sg.id
  from_port         = 5432
  to_port           = 5432
  ip_protocol          = "tcp"
  referenced_security_group_id = aws_security_group.zephyrwerk_api_sg.id
}

resource "aws_vpc_security_group_ingress_rule" "zephyrwerk_rds_from_pipeline_sg_ingress" {
  security_group_id = aws_security_group.zephyrwerk_rds_sg.id
  from_port         = 5432
  to_port           = 5432
  ip_protocol          = "tcp"
  referenced_security_group_id = aws_security_group.zephyrwerk_pipeline_sg.id
}

resource "aws_vpc_security_group_ingress_rule" "zephyrwerk_dashboard_sg_ingress" {
  security_group_id = aws_security_group.zephyrwerk_dashboard_sg.id
  from_port = 8501
  to_port = 8501
  cidr_ipv4 = "0.0.0.0/0"
  ip_protocol = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "zephyrwerk_api_from_dashboard_sg_ingress" {
  security_group_id = aws_security_group.zephyrwerk_api_sg.id
  from_port = 8000
  to_port = 8000
  ip_protocol = "tcp"
  referenced_security_group_id = aws_security_group.zephyrwerk_dashboard_sg.id
}