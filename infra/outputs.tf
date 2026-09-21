output "zephyrwerk_data_lake_bucket" {
  value       = aws_s3_bucket.zephyrwerk_data_lake.id
  description = "The name of the S3 bucket for Zephyrwerk data lake"
}