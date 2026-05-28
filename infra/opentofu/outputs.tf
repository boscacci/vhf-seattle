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

output "server_iam_policy_arn" {
  description = "Attach this policy to the private server role/user used for presigned URLs and public exports."
  value       = aws_iam_policy.server_s3_access.arn
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

output "dev_server_iam_policy_arn" {
  description = "Attach this policy to the private dev server role/user."
  value       = aws_iam_policy.dev_server_s3_access.arn
}

output "dev_cognito_user_pool_id" {
  description = "Dev Cognito user pool ID for mobile login."
  value       = aws_cognito_user_pool.dev_auth.id
}

output "dev_cognito_mobile_client_id" {
  description = "Public dev Cognito OAuth client ID for the mobile app."
  value       = aws_cognito_user_pool_client.dev_mobile.id
}

output "dev_cognito_domain" {
  description = "Dev Cognito hosted login domain."
  value       = local.dev_cognito_domain
}

output "dev_cognito_login_url" {
  description = "Dev Cognito hosted login URL using the first configured callback URL."
  value       = "${local.dev_cognito_domain}/oauth2/authorize?response_type=code&client_id=${aws_cognito_user_pool_client.dev_mobile.id}&redirect_uri=${urlencode(var.dev_auth_callback_urls[0])}&scope=openid+email+profile"
}

output "dev_cognito_allowed_email" {
  description = "Only approved dev Cognito user email."
  value       = var.dev_admin_email
}
