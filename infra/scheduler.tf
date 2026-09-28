resource "aws_scheduler_schedule" "zephyrwerk_daily_schedule" {
    name = var.daily_schedule_name

    flexible_time_window {
        mode = "OFF"
    }

    schedule_expression = "cron(0 6 * * ? *)"
    schedule_expression_timezone = "UTC"
    target {
        arn      = aws_sfn_state_machine.zephyrwerk_daily_pipeline.arn
        role_arn = aws_iam_role.zephyrwerk_scheduler_role.arn
    }
}

resource "aws_scheduler_schedule" "zephyrwerk_weekly_schedule" {
    name = var.weekly_schedule_name

    flexible_time_window {
        mode = "OFF"
    }

    schedule_expression = "cron(0 7 ? * MON *)"
    schedule_expression_timezone = "UTC"
    target {
        arn      = aws_sfn_state_machine.zephyrwerk_weekly_pipeline.arn
        role_arn = aws_iam_role.zephyrwerk_scheduler_role.arn
    }
}