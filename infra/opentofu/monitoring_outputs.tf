output "prod_clip_freshness_alarm_name" {
  description = "Non-paging CloudWatch diagnostic for stale production public clips."
  value       = aws_cloudwatch_metric_alarm.prod_clip_freshness.alarm_name
}

output "prod_public_manifest_freshness_alarm_name" {
  description = "CloudWatch alarm that detects a stalled production public manifest publisher"
  value       = aws_cloudwatch_metric_alarm.prod_public_manifest_freshness.alarm_name
}

output "prod_ais_freshness_alarm_name" {
  description = "CloudWatch alarm that detects stale production AIS ingest"
  value       = aws_cloudwatch_metric_alarm.prod_ais_freshness.alarm_name
}

output "prod_clip_freshness_alert_topic_arn" {
  description = "SNS topic for production public clip freshness alarm transitions."
  value       = aws_sns_topic.prod_clip_freshness_alerts.arn
}

output "prod_clip_freshness_function_name" {
  description = "Scheduled Lambda that publishes production public clip age."
  value       = aws_lambda_function.clip_freshness_monitor.function_name
}
