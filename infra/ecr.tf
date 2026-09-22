resource "aws_ecr_repository" "zephyrwerk_ecr" {
  for_each = var.ecr_container_names
  
  name = "zephyrwerk-${each.key}"

  image_tag_mutability = "IMMUTABLE"
  force_delete          = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name        = "zephyrwerk-${each.key}"
    Environment = "dev"
  }
}

resource "aws_ecr_lifecycle_policy" "zephyrwerk_ecr_lifecycle" {
  for_each = var.ecr_container_names

  repository = aws_ecr_repository.zephyrwerk_ecr[each.key].name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 5 images"
        selection    = {
          tagStatus     = "any"
          countType     = "imageCountMoreThan"
          countNumber   = 5
        }
        action       = {
          type = "expire"
        }
      }
    ]
  })
}