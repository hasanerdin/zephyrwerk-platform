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