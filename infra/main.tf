terraform {
  required_version = ">= 1.9"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile

  default_tags {
    tags = {
      Project     = "zephyrwerk"
    }
  }
}

resource "aws_s3_bucket" "zephyrwerk_data_lake" {
  bucket = var.s3_bucket_name
}

resource "aws_s3_bucket_public_access_block" "zephyrwerk_data_lake" {
  bucket = aws_s3_bucket.zephyrwerk_data_lake.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "zephyrwerk_data_lake" {
  bucket = aws_s3_bucket.zephyrwerk_data_lake.id
  versioning_configuration {
    status = "Disabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "zephyrwerk_data_lake" {
  bucket = aws_s3_bucket.zephyrwerk_data_lake.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}