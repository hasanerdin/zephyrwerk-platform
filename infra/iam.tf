resource "aws_iam_role" "ecs_execution"{
    name = var.ecs_execution_name

    assume_role_policy = jsonencode({
        Version = "2012-10-17"
        Statement = [
            {
                Action = "sts:AssumeRole"
                Effect = "Allow"
                Principal = {
                    Service = "ecs-tasks.amazonaws.com"
                }
            }
        ]
    })

    tags = {
        Name        = var.ecs_execution_name
        Environment = "dev"
    }
}

resource "aws_iam_role_policy_attachment" "ecs_execution_policy" {
    role       = aws_iam_role.ecs_execution.name
    policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "ecs_execution_secrets"{
    statement {
        actions = ["secretsmanager:GetSecretValue"]
        resources = [aws_secretsmanager_secret.zephyrwerk_rds_secret.arn]
    }
}

resource "aws_iam_role_policy" "ecs_execution_secrets" {
    name = "secrets-access"
    role = aws_iam_role.ecs_execution.id
    policy = data.aws_iam_policy_document.ecs_execution_secrets.json
}

resource "aws_cloudwatch_log_group" "ecs_execution_log_group" {
    name = var.cloudwatch_log_group_name
    retention_in_days = 7
}

# ECS task role for ingestion service
resource "aws_iam_role" "ecs_task_ingestion" {
    name = var.ecs_task_ingestion_name

    assume_role_policy = jsonencode({
        Version = "2012-10-17"
        Statement = [
            {
                Action = "sts:AssumeRole"
                Effect = "Allow"
                Principal = {
                    Service = "ecs-tasks.amazonaws.com"
                }
            }
        ]
    })

    tags = {
        Name        = var.ecs_task_ingestion_name
        Environment = "dev"
    }
}

data "aws_iam_policy_document" "ecs_task_ingestion" {
    statement {
        actions = ["s3:GetObject", "s3:PutObject"]
        resources = ["${aws_s3_bucket.zephyrwerk_data_lake.arn}/raw/*"]
    }

    statement {
        actions = ["s3:ListBucket"]
        resources = [aws_s3_bucket.zephyrwerk_data_lake.arn]
    }
}

resource "aws_iam_role_policy" "ecs_task_ingestion" {
    name = "ecs-task-ingestion"
    role = aws_iam_role.ecs_task_ingestion.id
    policy = data.aws_iam_policy_document.ecs_task_ingestion.json
}


# ECS task role for API service
resource "aws_iam_role" "ecs_task_api" {
    name = var.ecs_task_api_name

    assume_role_policy = jsonencode({
        Version = "2012-10-17"
        Statement = [
            {
                Action = "sts:AssumeRole"
                Effect = "Allow"
                Principal = {
                    Service = "ecs-tasks.amazonaws.com"
                }
            }
        ]
    })

    tags = {
        Name        = var.ecs_task_api_name
        Environment = "dev"
    }
}

data "aws_iam_policy_document" "ecs_task_api" {
    statement {
        actions = ["s3:GetObject"]
        resources = ["${aws_s3_bucket.zephyrwerk_data_lake.arn}/models/*"]
    }
}

resource "aws_iam_role_policy" "ecs_task_api" {
    name = "ecs-task-api"
    role = aws_iam_role.ecs_task_api.id
    policy = data.aws_iam_policy_document.ecs_task_api.json
}

# ECS task role for ML model training and inference
resource "aws_iam_role" "ecs_task_ml" {
    name = var.ecs_task_ml_name

    assume_role_policy = jsonencode({
        Version = "2012-10-17"
        Statement = [
            {
                Action = "sts:AssumeRole"
                Effect = "Allow"
                Principal = {
                    Service = "ecs-tasks.amazonaws.com"
                }
            }
        ]
    })

    tags = {
        Name        = var.ecs_task_ml_name
        Environment = "dev"
    }
}

data "aws_iam_policy_document" "ecs_task_ml" {
    statement {
        actions = ["s3:GetObject", "s3:PutObject"]
        resources = ["${aws_s3_bucket.zephyrwerk_data_lake.arn}/models/*"]
    }
}

resource "aws_iam_role_policy" "ecs_task_ml" {
    name = "ecs-task-ml"
    role = aws_iam_role.ecs_task_ml.id
    policy = data.aws_iam_policy_document.ecs_task_ml.json
}