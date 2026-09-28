locals {
    network_config = {
        AwsvpcConfiguration = {
            Subnets        = aws_subnet.public[*].id
            SecurityGroups = [aws_security_group.zephyrwerk_pipeline_sg.id]
            AssignPublicIp = "ENABLED"
        }
    }

    retry_config = [
        {
            ErrorEquals     = ["States.TaskFailed"]
            IntervalSeconds = 60
            MaxAttempts     = 2
            BackoffRate     = 2.0
        }
    ]
}

resource "aws_sfn_state_machine" "zephyrwerk_daily_pipeline" {
    name = var.daily_state_machine_name
    role_arn = aws_iam_role.zephyrwerk_step_function_role.arn

    definition = jsonencode(
        {
            StartAt = "Ingest",
            States = {
                Ingest = {
                    Type = "Parallel"
                    Branches = [
                        {
                            StartAt = "SmardFetch"
                            States = {
                                SmardFetch = {
                                    Type = "Task",
                                    Resource = "arn:aws:states:::ecs:runTask.sync",
                                    Parameters = {
                                        Cluster = aws_ecs_cluster.zephyrwerk_ecs.arn
                                        TaskDefinition = aws_ecs_task_definition.zephyrwerk_ingestion_task["smard"].arn
                                        LaunchType = "FARGATE"
                                        NetworkConfiguration = local.network_config
                                    },
                                    Retry = local.retry_config,
                                    End = true
                                }
                            }
                        },
                        
                        {
                            StartAt = "WeatherFetch"
                            States = {
                                WeatherFetch = {
                                    Type = "Task",
                                    Resource = "arn:aws:states:::ecs:runTask.sync",
                                    Parameters = {
                                        Cluster = aws_ecs_cluster.zephyrwerk_ecs.arn
                                        TaskDefinition = aws_ecs_task_definition.zephyrwerk_ingestion_task["weather"].arn
                                        LaunchType = "FARGATE"
                                        NetworkConfiguration = local.network_config
                                    },
                                    Retry = local.retry_config,
                                    End = true
                                }
                            }
                        },

                        {
                            StartAt = "WeatherForecastFetch"
                            States = {
                                WeatherForecastFetch = {
                                    Type = "Task",
                                    Resource = "arn:aws:states:::ecs:runTask.sync",
                                    Parameters = {
                                        Cluster = aws_ecs_cluster.zephyrwerk_ecs.arn
                                        TaskDefinition = aws_ecs_task_definition.zephyrwerk_ingestion_task["weather_forecast"].arn
                                        LaunchType = "FARGATE"
                                        NetworkConfiguration = local.network_config
                                    },
                                    Retry = local.retry_config,
                                    End = true
                                }
                            }
                        }
                    ]
                    Next = "Load"
                }

                Load = {
                    Type = "Task",
                    Resource = "arn:aws:states:::ecs:runTask.sync",
                    Parameters = {
                        Cluster = aws_ecs_cluster.zephyrwerk_ecs.arn
                        TaskDefinition = aws_ecs_task_definition.zephyrwerk_ingestion_task["load"].arn
                        LaunchType = "FARGATE"
                        NetworkConfiguration = local.network_config
                    },
                    Retry = local.retry_config,
                    Next = "Dbt"
                }

                Dbt = {
                    Type = "Task",
                    Resource = "arn:aws:states:::ecs:runTask.sync",
                    Parameters = {
                        Cluster = aws_ecs_cluster.zephyrwerk_ecs.arn
                        TaskDefinition = aws_ecs_task_definition.zephyrwerk_dbt_task.arn
                        LaunchType = "FARGATE"
                        NetworkConfiguration = local.network_config
                    },
                    Retry = local.retry_config,
                    End = true
                }
            }
        }
    )
}

resource "aws_sfn_state_machine" "zephyrwerk_weekly_pipeline" {
    name = var.weekly_state_machine_name
    role_arn = aws_iam_role.zephyrwerk_step_function_role.arn

    definition = jsonencode(
        {
            StartAt = "Train"
            States = {
                Train = {
                    Type = "Parallel"
                    Branches = [
                            {
                                StartAt = "TrainPrice"
                                States = {
                                    TrainPrice = {
                                        Type = "Task",
                                        Resource = "arn:aws:states:::ecs:runTask.sync",
                                        Parameters = {
                                            Cluster = aws_ecs_cluster.zephyrwerk_ecs.arn
                                            TaskDefinition = aws_ecs_task_definition.zephyrwerk_ml_task["price"].arn
                                            LaunchType = "FARGATE"
                                            NetworkConfiguration = local.network_config
                                        },
                                        Retry = local.retry_config,
                                        End = true
                                    }
                                }
                            },

                            {
                                StartAt = "TrainGeneration"
                                States = {
                                    TrainGeneration = {
                                        Type = "Task",
                                        Resource = "arn:aws:states:::ecs:runTask.sync",
                                        Parameters = {
                                            Cluster = aws_ecs_cluster.zephyrwerk_ecs.arn
                                            TaskDefinition = aws_ecs_task_definition.zephyrwerk_ml_task["generation"].arn
                                            LaunchType = "FARGATE"
                                            NetworkConfiguration = local.network_config
                                        },
                                        Retry = local.retry_config,
                                        End = true
                                    }
                                }
                            }   
                        ]
                    End = true
                }
            }
        }
    )
}