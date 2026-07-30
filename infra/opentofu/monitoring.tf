data "archive_file" "clip_freshness_monitor" {
  type        = "zip"
  output_path = "${path.module}/.terraform/talkingboats-clip-freshness-monitor.zip"

  source {
    filename = "talkingboats/__init__.py"
    content  = file("${path.module}/../../src/talkingboats/__init__.py")
  }

  source {
    filename = "talkingboats/stale_clip_monitor.py"
    content  = file("${path.module}/../../src/talkingboats/stale_clip_monitor.py")
  }
}

locals {
  clip_freshness_alarm_name = replace(
    "${var.project_name}-${var.resource_site_subdomain}-prod-public-clips-stale",
    ".",
    "-",
  )
  clip_freshness_lambda_name = replace(
    "${var.project_name}-${var.resource_site_subdomain}-prod-clip-freshness",
    ".",
    "-",
  )
  clip_freshness_namespace = "ElliottBayVHF"
}

data "aws_iam_policy_document" "clip_freshness_monitor_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "clip_freshness_monitor" {
  name               = local.clip_freshness_lambda_name
  assume_role_policy = data.aws_iam_policy_document.clip_freshness_monitor_assume_role.json

  tags = merge(local.common_tags, {
    Environment = "prod"
    Role        = "clip-freshness-monitor"
  })
}

resource "aws_iam_role_policy_attachment" "clip_freshness_monitor_basic_execution" {
  role       = aws_iam_role.clip_freshness_monitor.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "clip_freshness_monitor_access" {
  statement {
    sid       = "ReadPublicManifest"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.public_site.arn}/public_manifest.json"]
  }

  statement {
    sid       = "PublishFreshnessMetric"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = [local.clip_freshness_namespace]
    }
  }
}

resource "aws_iam_role_policy" "clip_freshness_monitor_access" {
  name   = "${local.clip_freshness_lambda_name}-access"
  role   = aws_iam_role.clip_freshness_monitor.id
  policy = data.aws_iam_policy_document.clip_freshness_monitor_access.json
}

resource "aws_cloudwatch_log_group" "clip_freshness_monitor" {
  name              = "/aws/lambda/${local.clip_freshness_lambda_name}"
  retention_in_days = 30

  tags = merge(local.common_tags, {
    Environment = "prod"
    Role        = "clip-freshness-monitor-logs"
  })
}

resource "aws_lambda_function" "clip_freshness_monitor" {
  function_name    = local.clip_freshness_lambda_name
  role             = aws_iam_role.clip_freshness_monitor.arn
  filename         = data.archive_file.clip_freshness_monitor.output_path
  source_code_hash = data.archive_file.clip_freshness_monitor.output_base64sha256
  runtime          = "python3.12"
  handler          = "talkingboats.stale_clip_monitor.lambda_handler"
  timeout          = 30
  memory_size      = 256

  environment {
    variables = {
      TALKINGBOATS_MONITOR_BUCKET              = aws_s3_bucket.public_site.bucket
      TALKINGBOATS_MONITOR_KEY                 = "public_manifest.json"
      TALKINGBOATS_MONITOR_NAMESPACE           = local.clip_freshness_namespace
      TALKINGBOATS_MONITOR_SITE                = local.site_fqdn
      TALKINGBOATS_MONITOR_STALE_AFTER_SECONDS = "3600"
    }
  }

  tags = merge(local.common_tags, {
    Environment = "prod"
    Role        = "clip-freshness-monitor"
  })

  depends_on = [
    aws_cloudwatch_log_group.clip_freshness_monitor,
    aws_iam_role_policy_attachment.clip_freshness_monitor_basic_execution,
    aws_iam_role_policy.clip_freshness_monitor_access,
  ]
}

resource "aws_cloudwatch_event_rule" "clip_freshness_monitor" {
  name                = local.clip_freshness_lambda_name
  description         = "Check the newest production public clip timestamp every five minutes"
  schedule_expression = "rate(5 minutes)"
  state               = "ENABLED"

  tags = merge(local.common_tags, {
    Environment = "prod"
    Role        = "clip-freshness-monitor-schedule"
  })
}

resource "aws_cloudwatch_event_target" "clip_freshness_monitor" {
  rule      = aws_cloudwatch_event_rule.clip_freshness_monitor.name
  target_id = "clip-freshness-monitor"
  arn       = aws_lambda_function.clip_freshness_monitor.arn
}

resource "aws_lambda_permission" "clip_freshness_monitor_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.clip_freshness_monitor.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.clip_freshness_monitor.arn
}

resource "aws_sns_topic" "prod_clip_freshness_alerts" {
  name         = local.clip_freshness_alarm_name
  display_name = "Seattle Boat Radio"

  tags = merge(local.common_tags, {
    Environment = "prod"
    Role        = "operator-alerts"
  })
}

data "aws_iam_policy_document" "prod_clip_freshness_alerts" {
  statement {
    sid    = "TopicOwnerManagement"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }

    actions = [
      "SNS:AddPermission",
      "SNS:DeleteTopic",
      "SNS:GetTopicAttributes",
      "SNS:ListSubscriptionsByTopic",
      "SNS:Publish",
      "SNS:RemovePermission",
      "SNS:SetTopicAttributes",
      "SNS:Subscribe",
    ]
    resources = [aws_sns_topic.prod_clip_freshness_alerts.arn]

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceOwner"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }

  statement {
    sid     = "AllowCloudWatchAlarmPublish"
    effect  = "Allow"
    actions = ["SNS:Publish"]

    principals {
      type        = "Service"
      identifiers = ["cloudwatch.amazonaws.com"]
    }

    resources = [aws_sns_topic.prod_clip_freshness_alerts.arn]

    condition {
      test     = "ArnLike"
      variable = "AWS:SourceArn"
      values = [
        "arn:aws:cloudwatch:${var.aws_region}:${data.aws_caller_identity.current.account_id}:alarm:${local.clip_freshness_alarm_name}",
      ]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_sns_topic_policy" "prod_clip_freshness_alerts" {
  arn    = aws_sns_topic.prod_clip_freshness_alerts.arn
  policy = data.aws_iam_policy_document.prod_clip_freshness_alerts.json
}

resource "aws_cloudwatch_metric_alarm" "prod_clip_freshness" {
  alarm_name          = local.clip_freshness_alarm_name
  alarm_description   = "Production seattleboatradio.com has no public clip newer than one hour, or its freshness monitor stopped reporting."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  datapoints_to_alarm = 1
  metric_name         = "LatestPublicClipAgeSeconds"
  namespace           = local.clip_freshness_namespace
  period              = 300
  statistic           = "Maximum"
  threshold           = 3600
  treat_missing_data  = "breaching"

  dimensions = {
    Environment = "prod"
    Site        = local.site_fqdn
  }

  alarm_actions = [aws_sns_topic.prod_clip_freshness_alerts.arn]
  ok_actions    = [aws_sns_topic.prod_clip_freshness_alerts.arn]

  tags = merge(local.common_tags, {
    Environment = "prod"
    Role        = "clip-freshness-alarm"
  })

  depends_on = [aws_sns_topic_policy.prod_clip_freshness_alerts]
}
