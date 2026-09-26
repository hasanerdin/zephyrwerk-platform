resource "aws_ecs_cluster" "zephyrwerk_ecs" {
  name = var.ecs_cluster_name

  tags = {
    Name        = var.ecs_cluster_name
    Environment = "dev"
  }

  service_connect_defaults {
    namespace = aws_service_discovery_http_namespace.zephyrwerk.arn
  }
}

resource "aws_service_discovery_http_namespace" "zephyrwerk" {
  name = "zephyrwerk"
  description = "Service Connect namespace for Zephyrwerk services"
}

resource "aws_ecs_service" "api" {
  name                = "zephyrwerk-api"
  cluster             = aws_ecs_cluster.zephyrwerk_ecs.id
  task_definition     = aws_ecs_task_definition.zephyrwerk_api_task.arn
  desired_count       = 1
  launch_type         = "FARGATE"

  network_configuration {
    subnets           = aws_subnet.public[*].id
    security_groups   = [aws_security_group.zephyrwerk_api_sg.id] 
    assign_public_ip  = true
  }

  service_connect_configuration {
    enabled = true

    service {
      port_name       = "api"
      discovery_name  = "api"

      client_alias {
        port      = 8000
        dns_name  = "api"
      }
    }
  }
}

resource "aws_ecs_service" "dashboard" {
  name                  = "zephyrwerk-dashboard"
  cluster               = aws_ecs_cluster.zephyrwerk_ecs.id
  task_definition       = aws_ecs_task_definition.zephyrwerk_dashboard_task.arn
  desired_count         = 1
  launch_type           = "FARGATE"
  depends_on            = [aws_ecs_service.api]

  network_configuration {
    subnets         = aws_subnet.public[*].id
    security_groups = [aws_security_group.zephyrwerk_dashboard_sg.id]
    assign_public_ip = true
  }

  service_connect_configuration {
    enabled = true
  }
}

resource "aws_ecs_task_definition" "zephyrwerk_init_db_task" {
  family                   = "zephyrwerk-init-db"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.ecs_execution.arn

  runtime_platform {
    cpu_architecture        = "ARM64"
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([
    {
      name      = "init-db"
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
          awslogs-stream-prefix = "init-db"
        }
      }

      command = ["python", "-m", "ingestion", "--task", "init-db"]
    }
  ])
}

resource "aws_ecs_task_definition" "zephyrwerk_ingestion_task" {
  for_each = var.ingestion_tasks
  family                   = "zephyrwerk-ingestion-${each.key}"
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
      name      = "ingestion-${each.key}"
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
          value = aws_s3_bucket.zephyrwerk_data_lake.bucket
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
          awslogs-stream-prefix = "ingestion-${each.key}"
        }
      }

      command = each.value
    }
  ])
}

resource "aws_ecs_task_definition" "zephyrwerk_dbt_task" {
  family                   = "zephyrwerk-dbt"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  runtime_platform {
    cpu_architecture        = "ARM64"
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([
    {
      name      = "dbt"
      image     = "${aws_ecr_repository.zephyrwerk_ecr["dbt"].repository_url}:${var.image_tag}"
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
          awslogs-stream-prefix = "dbt"
        }
      }

      command = ["/bin/sh", "-c", join(" && ", var.dbt_tasks)]
    }
  ])
}

resource "aws_ecs_task_definition" "zephyrwerk_ml_task" {
  for_each = var.ml_tasks
  family                   = "zephyrwerk-ml-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "1024"
  memory                   = "4096"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task_ml.arn
  runtime_platform {
    cpu_architecture        = "ARM64"
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([
    {
      name      = "ml-${each.key}"
      image     = "${aws_ecr_repository.zephyrwerk_ecr["ml"].repository_url}:${var.image_tag}"
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
          value = aws_s3_bucket.zephyrwerk_data_lake.bucket
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
          awslogs-stream-prefix = "ml-${each.key}"
        }
      }

      command = each.value
    }
  ])
}

resource "aws_ecs_task_definition" "zephyrwerk_api_task" {
  family                    = "zephyrwerk-api"
  requires_compatibilities  = ["FARGATE"]
  network_mode              = "awsvpc"
  cpu                       = "512"
  memory                    = "1024"
  execution_role_arn        = aws_iam_role.ecs_execution.arn
  task_role_arn             = aws_iam_role.ecs_task_api.arn
  runtime_platform {
    cpu_architecture        = "ARM64"
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([
    {
      name      = "api"
      image     = "${aws_ecr_repository.zephyrwerk_ecr["api"].repository_url}:${var.image_tag}"
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
          value = aws_s3_bucket.zephyrwerk_data_lake.bucket
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
          awslogs-stream-prefix = "api"
        }
      }

      portMappings = [
        {
          name          = "api"
          containerPort = 8000
          protocol      = "tcp"
        }
      ]

      healthCheck = {
        command     = ["CMD-SHELL", "python -c \"import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status == 200 else 1)\""]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 10
      }
    }
  ])
}

resource "aws_ecs_task_definition" "zephyrwerk_dashboard_task" {
  family                    = "zephyrwerk-dashboard"
  requires_compatibilities  = ["FARGATE"]
  network_mode              = "awsvpc"
  cpu                       = "512"
  memory                    = "1024"
  execution_role_arn        = aws_iam_role.ecs_execution.arn
  runtime_platform {
    cpu_architecture        = "ARM64"
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode ([
    {
      name = "dashboard"
      image = "${aws_ecr_repository.zephyrwerk_ecr["dashboard"].repository_url}:${var.image_tag}"
      essential = true

      environment = [
        {
          name = "ZEPHYRWERK_DASHBOARD_API_URL"
          value = "http://api:8000"
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options   = {
          awslogs-group         = var.cloudwatch_log_group_name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "dashboard"
        }
      }

      portMappings = [
        {
          name = "dashboard"
          containerPort = 8501
          protocol = "tcp"
        }
      ]

      healthCheck = {
        command     = ["CMD-SHELL", "python -c \"import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8501/_stcore/health').status == 200 else 1)\""]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 10
      }
    }
  ])
}

