variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "eu-central-1"
}

variable "aws_profile" {
  description = "AWS profile to use for authentication"
  type        = string
  default     = "zephyrwerk"
}

variable "s3_bucket_name" {
  description = "Name of the S3 bucket for Zephyrwerk data lake"
  type        = string
  default     = "zephyrwerk-data-lake"
}

variable "vpc_name" {
  description = "Name of the VPC"
  type        = string
  default     = "zephyrwerk-vpc"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "private_subnets" {
  description = "List of private subnet CIDR blocks"
  type        = list(string)
  default     = ["10.0.11.0/24", "10.0.12.0/24"]
}

variable "public_subnets" {
  description = "List of public subnet CIDR blocks"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "pipeline_sg" {
  description = "Security group for the pipeline"
  type        = string
  default     = "zephyrwerk-pipeline-sg"
}

variable "api_sg" {
  description = "Security group for the API"
  type        = string
  default     = "zephyrwerk-api-sg"
}

variable "rds_sg" {
  description = "Security group for the database"
  type        = string
  default     = "zephyrwerk-rds-sg"
}

variable "rds_subnet_group" {
  description = "Name of the RDS subnet group"
  type        = string
  default     = "zephyrwerk-rds-subnet-group"
}

variable "rds_username" {
  description = "Username for the RDS database"
  type        = string
  default     = "zephyrwerk_admin"
}

variable "ecr_container_names" {
  description = "List of container names for the ECR repositories"
  type        = set(string)
  default     = ["api", "dashboard", "ingestion", "dbt", "ml"]
}

variable "ecs_execution_name" {
  description = "Name of the ECS execution role"
  type        = string
  default     = "zephyrwerk-ecs-role-execution"
}

variable "ecs_task_ingestion_name" {
  description = "Name of the ECS task role for ingestion service"
  type        = string
  default     = "zephyrwerk-ecs-task-role-ingestion"
}

variable "ecs_task_api_name" {
  description = "Name of the ECS task role for API service"
  type        = string
  default     = "zephyrwerk-ecs-task-role-api"
}

variable "ecs_task_ml_name" {
  description = "Name of the ECS task role for ML model training and inference"
  type        = string
  default     = "zephyrwerk-ecs-task-role-ml"
}

variable "cloudwatch_log_group_name" {
  description = "Name of the CloudWatch log group for the pipeline"
  type        = string
  default     = "/zephyrwerk/pipeline"
}

variable "ecs_cluster_name" {
  description = "Name of the ECS cluster"
  type        = string
  default     = "zephyrwerk-cluster"
}

variable "image_tag" {
  description = "Tag for the Docker images"
  type        = string
  default     = "071e25e"
}

variable "smard_base_url" {
  description = "Base URL for the SMARD API"
  type        = string
  default     = "https://www.smard.de/app/chart_data"
}

variable "openmeteo_forecast_url" {
  description = "Base URL for the Open-Meteo forecast API"
  type        = string
  default     = "https://api.open-meteo.com/v1/forecast"
}

variable "openmeteo_history_url" {
  description = "Base URL for the Open-Meteo historical data API"
  type        = string
  default     = "https://archive-api.open-meteo.com/v1/archive"
}

variable "ingestion_tasks" {
  description = "Map of ingestion tasks and their corresponding command line arguments"
  type        = map(list(string))
  default = {
      smard = ["python", "-m", "ingestion", "--task", "smard"],
      weather_forecast = ["python", "-m", "ingestion", "--task", "weather_forecast"],
      weather = ["python", "-m", "ingestion", "--task", "weather"],
      load = ["python", "-m", "ingestion", "--task", "load"]
  }
}

variable "dbt_tasks" {
  description = "List of dbt tasks to run"
  type        = list(string)
  default     = ["dbt seed --profiles-dir .", "dbt run --profiles-dir . ", "dbt test --profiles-dir ."]
}

variable "ml_tasks" {
  description = "Map of ml tasks and their corresponding command line arguments"
  type = map(list(string))
  default = {
    price = ["python", "-m", "ml.train_price_model"],
    generation = ["python", "-m", "ml.train_generation_model"]
  }
}

variable "dashboard_sg" {
  description = "Security group for the dashboard"
  type        = string
  default     = "zephyrwerk-dashboard-sg"
}

variable "ecs_step_function_name" {
  description = "Name of the ECS Step Function role"
  type        = string
  default     = "zephyrwerk-step-function-role"
}

variable "daily_state_machine_name" {
  description = "Name of daily AWS state machine"
  type = string
  default = "zephyrwerk-daily-pipeline"
}

variable "weekly_state_machine_name"{
  description = "Name of weekly AWS state machine"
  type = string
  default = "zephyrwerk-weekly-pipeline"
}

variable "scheduler_name" {
  description = "Name of EventBridge Scheduler"
  type = string
  default = "zephyrwerk-scheduler"
}

variable "daily_schedule_name" {
  description = "Name of daily schedule"
  type = string
  default = "zephyrwerk-daily-schedule"
}

variable "weekly_schedule_name" {
  description = "Name of daily schedule"
  type = string
  default = "zephyrwerk-weekly-schedule"
}