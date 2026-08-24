# Materialize public clip and queue totals from the existing serving indexes.
# The API flag remains off until the corresponding table has been backfilled
# and validated in that environment.

data "archive_file" "clip_count_aggregator" {
  type        = "zip"
  output_path = "${path.module}/.terraform/talkingboats-clip-count-aggregator.zip"

  source {
    filename = "talkingboats/__init__.py"
    content  = file("${path.module}/../../src/talkingboats/__init__.py")
  }

  source {
    filename = "talkingboats/clip_count_aggregates.py"
    content  = file("${path.module}/../../src/talkingboats/clip_count_aggregates.py")
  }
}

locals {
  clip_count_source_index_pks = concat(
    ["clips#transcribed", "clips#featured"],
    [for status in ["pending", "processing", "waiting_upload", "error"] : "clip_status#${status}"],
  )
  clip_count_aggregator_prod_lambda_name = replace(
    "${var.project_name}-${var.resource_site_subdomain}-clip-count-aggregator",
    ".",
    "-",
  )
  clip_count_aggregator_dev_lambda_name = replace(
    "${var.project_name}-${var.dev_resource_site_subdomain}-clip-count-aggregator",
    ".",
    "-",
  )
  clip_count_aggregator_error_alarm_name = replace(
    "${var.project_name}-${var.resource_site_subdomain}-prod-clip-count-aggregate-errors",
    ".",
    "-",
  )
  clip_count_aggregator_lag_alarm_name = replace(
    "${var.project_name}-${var.resource_site_subdomain}-prod-clip-count-aggregate-lag",
    ".",
    "-",
  )
  clip_count_aggregator_dev_error_alarm_name = replace(
    "${var.project_name}-${var.dev_resource_site_subdomain}-clip-count-aggregate-errors",
    ".",
    "-",
  )
  clip_count_aggregator_dev_lag_alarm_name = replace(
    "${var.project_name}-${var.dev_resource_site_subdomain}-clip-count-aggregate-lag",
    ".",
    "-",
  )
}

data "aws_iam_policy_document" "clip_count_aggregator_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "clip_count_aggregator_prod" {
  name               = "${local.clip_count_aggregator_prod_lambda_name}-role"
  assume_role_policy = data.aws_iam_policy_document.clip_count_aggregator_assume_role.json

  tags = merge(local.common_tags, {
    Environment = "prod"
    Role        = "clip-count-aggregator"
  })
}

resource "aws_iam_role" "clip_count_aggregator_dev" {
  name               = "${local.clip_count_aggregator_dev_lambda_name}-role"
  assume_role_policy = data.aws_iam_policy_document.clip_count_aggregator_assume_role.json

  tags = merge(local.common_tags, {
    Environment = "dev"
    Role        = "clip-count-aggregator"
  })
}

resource "aws_iam_role_policy_attachment" "clip_count_aggregator_prod_basic_execution" {
  role       = aws_iam_role.clip_count_aggregator_prod.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "clip_count_aggregator_dev_basic_execution" {
  role       = aws_iam_role.clip_count_aggregator_dev.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "clip_count_aggregator_prod_stream_execution" {
  role       = aws_iam_role.clip_count_aggregator_prod.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaDynamoDBExecutionRole"
}

resource "aws_iam_role_policy_attachment" "clip_count_aggregator_dev_stream_execution" {
  role       = aws_iam_role.clip_count_aggregator_dev.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaDynamoDBExecutionRole"
}

data "aws_iam_policy_document" "clip_count_aggregator_prod_access" {
  statement {
    sid = "ReconcileProductionClipCountAggregate"
    actions = [
      "dynamodb:ConditionCheckItem",
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:TransactWriteItems",
      "dynamodb:UpdateItem",
    ]
    resources = [aws_dynamodb_table.radio_events.arn]
  }
}

data "aws_iam_policy_document" "clip_count_aggregator_dev_access" {
  statement {
    sid = "ReconcileDevClipCountAggregate"
    actions = [
      "dynamodb:ConditionCheckItem",
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:TransactWriteItems",
      "dynamodb:UpdateItem",
    ]
    resources = [aws_dynamodb_table.dev_radio_events.arn]
  }
}

resource "aws_iam_role_policy" "clip_count_aggregator_prod_access" {
  name   = "${local.clip_count_aggregator_prod_lambda_name}-access"
  role   = aws_iam_role.clip_count_aggregator_prod.id
  policy = data.aws_iam_policy_document.clip_count_aggregator_prod_access.json
}

resource "aws_iam_role_policy" "clip_count_aggregator_dev_access" {
  name   = "${local.clip_count_aggregator_dev_lambda_name}-access"
  role   = aws_iam_role.clip_count_aggregator_dev.id
  policy = data.aws_iam_policy_document.clip_count_aggregator_dev_access.json
}

resource "aws_cloudwatch_log_group" "clip_count_aggregator_prod" {
  name              = "/aws/lambda/${local.clip_count_aggregator_prod_lambda_name}"
  retention_in_days = 30

  tags = merge(local.common_tags, {
    Environment = "prod"
    Role        = "clip-count-aggregator-logs"
  })
}

resource "aws_cloudwatch_log_group" "clip_count_aggregator_dev" {
  name              = "/aws/lambda/${local.clip_count_aggregator_dev_lambda_name}"
  retention_in_days = 30

  tags = merge(local.common_tags, {
    Environment = "dev"
    Role        = "clip-count-aggregator-logs"
  })
}

resource "aws_lambda_function" "clip_count_aggregator_prod" {
  function_name                  = local.clip_count_aggregator_prod_lambda_name
  role                           = aws_iam_role.clip_count_aggregator_prod.arn
  filename                       = data.archive_file.clip_count_aggregator.output_path
  source_code_hash               = data.archive_file.clip_count_aggregator.output_base64sha256
  runtime                        = "python3.12"
  handler                        = "talkingboats.clip_count_aggregates.lambda_handler"
  timeout                        = 30
  memory_size                    = 256
  reserved_concurrent_executions = 2

  environment {
    variables = {
      TALKINGBOATS_AWS_REGION       = var.aws_region
      TALKINGBOATS_CLIP_COUNT_TABLE = aws_dynamodb_table.radio_events.name
    }
  }

  tags = merge(local.common_tags, {
    Environment = "prod"
    Role        = "clip-count-aggregator"
  })

  depends_on = [
    aws_cloudwatch_log_group.clip_count_aggregator_prod,
    aws_iam_role_policy_attachment.clip_count_aggregator_prod_basic_execution,
    aws_iam_role_policy_attachment.clip_count_aggregator_prod_stream_execution,
    aws_iam_role_policy.clip_count_aggregator_prod_access,
  ]
}

resource "aws_lambda_function" "clip_count_aggregator_dev" {
  function_name                  = local.clip_count_aggregator_dev_lambda_name
  role                           = aws_iam_role.clip_count_aggregator_dev.arn
  filename                       = data.archive_file.clip_count_aggregator.output_path
  source_code_hash               = data.archive_file.clip_count_aggregator.output_base64sha256
  runtime                        = "python3.12"
  handler                        = "talkingboats.clip_count_aggregates.lambda_handler"
  timeout                        = 30
  memory_size                    = 256
  reserved_concurrent_executions = 2

  environment {
    variables = {
      TALKINGBOATS_AWS_REGION       = var.aws_region
      TALKINGBOATS_CLIP_COUNT_TABLE = aws_dynamodb_table.dev_radio_events.name
    }
  }

  tags = merge(local.common_tags, {
    Environment = "dev"
    Role        = "clip-count-aggregator"
  })

  depends_on = [
    aws_cloudwatch_log_group.clip_count_aggregator_dev,
    aws_iam_role_policy_attachment.clip_count_aggregator_dev_basic_execution,
    aws_iam_role_policy_attachment.clip_count_aggregator_dev_stream_execution,
    aws_iam_role_policy.clip_count_aggregator_dev_access,
  ]
}

resource "aws_lambda_event_source_mapping" "clip_count_aggregator_prod" {
  event_source_arn                   = aws_dynamodb_table.radio_events.stream_arn
  function_name                      = aws_lambda_function.clip_count_aggregator_prod.arn
  starting_position                  = "LATEST"
  batch_size                         = 100
  maximum_batching_window_in_seconds = 2
  function_response_types            = ["ReportBatchItemFailures"]

  filter_criteria {
    filter {
      pattern = jsonencode({
        dynamodb = {
          Keys = {
            pk = {
              S = local.clip_count_source_index_pks
            }
          }
        }
      })
    }
  }

  depends_on = [aws_lambda_function.clip_count_aggregator_prod]
}

resource "aws_lambda_event_source_mapping" "clip_count_aggregator_dev" {
  event_source_arn                   = aws_dynamodb_table.dev_radio_events.stream_arn
  function_name                      = aws_lambda_function.clip_count_aggregator_dev.arn
  starting_position                  = "LATEST"
  batch_size                         = 100
  maximum_batching_window_in_seconds = 2
  function_response_types            = ["ReportBatchItemFailures"]

  filter_criteria {
    filter {
      pattern = jsonencode({
        dynamodb = {
          Keys = {
            pk = {
              S = local.clip_count_source_index_pks
            }
          }
        }
      })
    }
  }

  depends_on = [aws_lambda_function.clip_count_aggregator_dev]
}

resource "aws_cloudwatch_metric_alarm" "clip_count_aggregator_prod_errors" {
  alarm_name          = local.clip_count_aggregator_error_alarm_name
  alarm_description   = "Production clip-count aggregate Lambda returned an error. Count reads will remain deferred until the stream catches up."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  datapoints_to_alarm = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.clip_count_aggregator_prod.function_name
  }

  alarm_actions = [aws_sns_topic.prod_clip_freshness_alerts.arn]
  ok_actions    = [aws_sns_topic.prod_clip_freshness_alerts.arn]

  tags = merge(local.common_tags, {
    Environment = "prod"
    Role        = "clip-count-aggregate-error-alarm"
  })

  depends_on = [aws_sns_topic_policy.prod_clip_freshness_alerts]
}

resource "aws_cloudwatch_metric_alarm" "clip_count_aggregator_prod_lag" {
  alarm_name          = local.clip_count_aggregator_lag_alarm_name
  alarm_description   = "Production clip-count aggregate stream is more than five minutes behind. Count reads may be stale."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  datapoints_to_alarm = 1
  metric_name         = "IteratorAge"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Maximum"
  threshold           = 300000
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.clip_count_aggregator_prod.function_name
  }

  alarm_actions = [aws_sns_topic.prod_clip_freshness_alerts.arn]
  ok_actions    = [aws_sns_topic.prod_clip_freshness_alerts.arn]

  tags = merge(local.common_tags, {
    Environment = "prod"
    Role        = "clip-count-aggregate-lag-alarm"
  })

  depends_on = [aws_sns_topic_policy.prod_clip_freshness_alerts]
}

# The current public/private runtime intentionally uses the isolated dev table
# as its serving table. Alert on its stream consumer as a production-serving
# dependency until that routing is migrated to the nominal prod table.
resource "aws_cloudwatch_metric_alarm" "clip_count_aggregator_dev_errors" {
  alarm_name          = local.clip_count_aggregator_dev_error_alarm_name
  alarm_description   = "Serving-table clip-count aggregate Lambda returned an error. Count reads will remain deferred until the stream catches up."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  datapoints_to_alarm = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.clip_count_aggregator_dev.function_name
  }

  alarm_actions = [aws_sns_topic.prod_clip_freshness_alerts.arn]
  ok_actions    = [aws_sns_topic.prod_clip_freshness_alerts.arn]

  tags = merge(local.common_tags, {
    Environment = "dev"
    Role        = "clip-count-aggregate-error-alarm"
  })

  depends_on = [aws_sns_topic_policy.prod_clip_freshness_alerts]
}

resource "aws_cloudwatch_metric_alarm" "clip_count_aggregator_dev_lag" {
  alarm_name          = local.clip_count_aggregator_dev_lag_alarm_name
  alarm_description   = "Serving-table clip-count aggregate stream is more than five minutes behind. Count reads may be stale."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  datapoints_to_alarm = 1
  metric_name         = "IteratorAge"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Maximum"
  threshold           = 300000
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.clip_count_aggregator_dev.function_name
  }

  alarm_actions = [aws_sns_topic.prod_clip_freshness_alerts.arn]
  ok_actions    = [aws_sns_topic.prod_clip_freshness_alerts.arn]

  tags = merge(local.common_tags, {
    Environment = "dev"
    Role        = "clip-count-aggregate-lag-alarm"
  })

  depends_on = [aws_sns_topic_policy.prod_clip_freshness_alerts]
}
