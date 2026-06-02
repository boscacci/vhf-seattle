output "site_fqdn" {
  description = "Public site hostname."
  value       = local.site_fqdn
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID for invalidations."
  value       = aws_cloudfront_distribution.site.id
}

output "cloudfront_domain_name" {
  description = "CloudFront distribution domain name."
  value       = aws_cloudfront_distribution.site.domain_name
}

output "public_site_bucket" {
  description = "Private S3 bucket used as the CloudFront static-site origin."
  value       = aws_s3_bucket.public_site.bucket
}

output "raw_audio_bucket" {
  description = "Private raw-audio S3 bucket."
  value       = aws_s3_bucket.raw_audio.bucket
}

output "radio_events_table_name" {
  description = "DynamoDB table for durable prod radio, AIS, and telemetry event records."
  value       = aws_dynamodb_table.radio_events.name
}

output "dev_site_fqdn" {
  description = "Dev public site hostname."
  value       = local.dev_site_fqdn
}

output "dev_cloudfront_distribution_id" {
  description = "Dev CloudFront distribution ID for invalidations."
  value       = aws_cloudfront_distribution.dev_site.id
}

output "dev_cloudfront_domain_name" {
  description = "Dev CloudFront distribution domain name."
  value       = aws_cloudfront_distribution.dev_site.domain_name
}

output "dev_public_site_bucket" {
  description = "Private S3 bucket used as the dev CloudFront static-site origin."
  value       = aws_s3_bucket.dev_public_site.bucket
}

output "dev_raw_audio_bucket" {
  description = "Private dev raw-audio S3 bucket."
  value       = aws_s3_bucket.dev_raw_audio.bucket
}

output "dev_radio_events_table_name" {
  description = "DynamoDB table for durable dev radio, AIS, and telemetry event records."
  value       = aws_dynamodb_table.dev_radio_events.name
}
