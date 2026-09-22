output "zephyrwerk_data_lake_bucket" {
  value       = aws_s3_bucket.zephyrwerk_data_lake.id
  description = "The name of the S3 bucket for Zephyrwerk data lake"
}

output "zephyrwerk_rds_address" {
  value       = aws_db_instance.zephyrwerk_rds.address
  description = "The address of the Zephyrwerk RDS instance"
}

output "ecr_repository_urls" {
  value       = { for name, repo in aws_ecr_repository.zephyrwerk_ecr : name => repo.repository_url }
  description = "The URLs of the ECR repositories for Zephyrwerk"
}