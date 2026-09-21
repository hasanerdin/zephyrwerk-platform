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