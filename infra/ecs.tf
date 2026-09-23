resource "aws_ecs_cluster" "zephyrwerk_ecs" {
  name = var.ecs_cluster_name

  tags = {
    Name        = var.ecs_cluster_name
    Environment = "dev"
  }
}

resource "aws_ecs_task_definition" "zephyrwerk_ingestion_task" {
  family                   = "zephyrwerk-loader"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task_ingestion.arn
  runtime_platform {
    cpu_architecture        = "ARM64"
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([
    {
      name      = "loader"
      image     = "${aws_ecr_repository.zephyrwerk_ecr["ingestion"].repository_url}:${var.image_tag}"
      essential = true
      
      environment = [
        {
          name  = "ZEPHYRWERK_RDS_HOST"
          value = aws_db_instance.zephyrwerk_rds.address
        },
        {
          name  = "ZEPHYRWERK_RDS_PORT"
          value = tostring(aws_db_instance.zephyrwerk_rds.port)
        },
        {
          name  = "ZEPHYRWERK_RDS_DB"
          value = aws_db_instance.zephyrwerk_rds.db_name
        },
        {
          name  = "ZEPHYRWERK_RDS_USER"
          value = var.rds_username
        },
        {
            name = "ZEPHYRWERK_AWS_BUCKET_NAME"
            value = aws_s3_bucket.zephyrwerk_data_lake.id
        },
        {
            name = "ZEPHYRWERK_SMARD_BASE_URL"
            value = var.smard_base_url
        },
        {
            name = "ZEPHYRWERK_OPENMETEO_FORECAST_URL"
            value = var.openmeteo_forecast_url
        },
        {
            name = "ZEPHYRWERK_OPENMETEO_HISTORY_URL"
            value = var.openmeteo_history_url
        },
        {
            name = "AWS_ACCESS_KEY_ID"
            value = ""
        },
        {
            name = "AWS_SECRET_ACCESS_KEY"
            value = ""
        },
        {
            name = "ZEPHYRWERK_API_HOST"
            value = "0.0.0.0"
        },
        {
            name = "ZEPHYRWERK_API_PORT"
            value = "8000"
        },
        {
            name = "ZEPHYRWERK_DASHBOARD_API_URL"
            value = "http://localhost:8000"
        }
      ]

      secrets = [
        {
          name      = "ZEPHYRWERK_RDS_PASSWORD"
          valueFrom = "${aws_secretsmanager_secret.zephyrwerk_rds_secret.arn}:password::"
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options   = {
          awslogs-group         = var.cloudwatch_log_group_name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "loader"
        }
      }

      command = ["python", "-m", "ingestion", "--task", "load"]
    }
  ])
}