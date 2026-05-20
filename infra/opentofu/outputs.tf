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

output "server_iam_policy_arn" {
  description = "Attach this policy to the private server role/user used for presigned URLs and public exports."
  value       = aws_iam_policy.server_s3_access.arn
}
