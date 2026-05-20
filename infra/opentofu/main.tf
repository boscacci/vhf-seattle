data "aws_caller_identity" "current" {}

data "aws_route53_zone" "root" {
  name         = "${var.root_domain}."
  private_zone = false
}

data "aws_cloudfront_cache_policy" "caching_optimized" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_cache_policy" "caching_disabled" {
  name = "Managed-CachingDisabled"
}

locals {
  site_fqdn        = "${var.site_subdomain}.${var.root_domain}"
  bucket_base      = replace("${var.project_name}-${var.site_subdomain}", ".", "-")
  public_bucket    = coalesce(var.public_site_bucket_name, "${local.bucket_base}-${data.aws_caller_identity.current.account_id}-public")
  raw_audio_bucket = coalesce(var.raw_audio_bucket_name, "${local.bucket_base}-${data.aws_caller_identity.current.account_id}-raw")
  origin_id        = "s3-public-site"
}

resource "aws_s3_bucket" "public_site" {
  bucket        = local.public_bucket
  force_destroy = var.force_destroy_buckets

  tags = {
    Project = var.project_name
    Role    = "public-static-site"
  }
}

resource "aws_s3_bucket" "raw_audio" {
  bucket        = local.raw_audio_bucket
  force_destroy = var.force_destroy_buckets

  tags = {
    Project = var.project_name
    Role    = "private-raw-audio"
  }
}

resource "aws_s3_bucket_public_access_block" "public_site" {
  bucket                  = aws_s3_bucket.public_site.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_public_access_block" "raw_audio" {
  bucket                  = aws_s3_bucket.raw_audio.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "public_site" {
  bucket = aws_s3_bucket.public_site.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "raw_audio" {
  bucket = aws_s3_bucket.raw_audio.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "public_site" {
  bucket = aws_s3_bucket.public_site.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_versioning" "raw_audio" {
  bucket = aws_s3_bucket.raw_audio.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "raw_audio" {
  bucket = aws_s3_bucket.raw_audio.id

  rule {
    id     = "expire-raw-audio"
    status = "Enabled"

    filter {
      prefix = "raw/"
    }

    expiration {
      days = var.raw_retention_days
    }

    noncurrent_version_expiration {
      noncurrent_days = var.raw_retention_days
    }
  }
}

resource "aws_acm_certificate" "site" {
  provider          = aws.us_east_1
  domain_name       = local.site_fqdn
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Project = var.project_name
  }
}

resource "aws_route53_record" "site_cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.site.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  zone_id = data.aws_route53_zone.root.zone_id
  name    = each.value.name
  type    = each.value.type
  ttl     = 60
  records = [each.value.record]

  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "site" {
  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.site.arn
  validation_record_fqdns = [for record in aws_route53_record.site_cert_validation : record.fqdn]
}

resource "aws_cloudfront_origin_access_control" "public_site" {
  name                              = "${local.site_fqdn}-s3-oac"
  description                       = "CloudFront-only access to the Talking Boats static site bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "site" {
  enabled             = true
  comment             = "Talking Boats public static site"
  aliases             = [local.site_fqdn]
  default_root_object = "index.html"
  is_ipv6_enabled     = true
  price_class         = "PriceClass_100"

  origin {
    domain_name              = aws_s3_bucket.public_site.bucket_regional_domain_name
    origin_id                = local.origin_id
    origin_access_control_id = aws_cloudfront_origin_access_control.public_site.id
  }

  default_cache_behavior {
    target_origin_id       = local.origin_id
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    cache_policy_id        = data.aws_cloudfront_cache_policy.caching_optimized.id
  }

  ordered_cache_behavior {
    path_pattern           = "public_manifest.json"
    target_origin_id       = local.origin_id
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    cache_policy_id        = data.aws_cloudfront_cache_policy.caching_disabled.id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.site.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  depends_on = [aws_acm_certificate_validation.site]
}

data "aws_iam_policy_document" "public_site_cloudfront_read" {
  statement {
    sid     = "AllowCloudFrontRead"
    actions = ["s3:GetObject"]

    resources = ["${aws_s3_bucket.public_site.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.site.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "public_site" {
  bucket = aws_s3_bucket.public_site.id
  policy = data.aws_iam_policy_document.public_site_cloudfront_read.json
}

data "aws_iam_policy_document" "server_s3_access" {
  statement {
    sid = "ListProjectBuckets"
    actions = [
      "s3:ListBucket",
    ]
    resources = [
      aws_s3_bucket.raw_audio.arn,
      aws_s3_bucket.public_site.arn,
    ]
  }

  statement {
    sid = "ManagePrivateAudioObjects"
    actions = [
      "s3:DeleteObject",
      "s3:GetObject",
      "s3:PutObject",
    ]
    resources = [
      "${aws_s3_bucket.raw_audio.arn}/raw/*",
      "${aws_s3_bucket.raw_audio.arn}/hall-of-fame/*",
    ]
  }

  statement {
    sid = "PublishReviewedStaticSite"
    actions = [
      "s3:DeleteObject",
      "s3:GetObject",
      "s3:PutObject",
    ]
    resources = ["${aws_s3_bucket.public_site.arn}/*"]
  }

  statement {
    sid = "InvalidatePublicDistribution"
    actions = [
      "cloudfront:CreateInvalidation",
    ]
    resources = [aws_cloudfront_distribution.site.arn]
  }
}

resource "aws_iam_policy" "server_s3_access" {
  name        = "${var.project_name}-server-s3-access"
  description = "Least-privilege S3/CloudFront access for the private Talking Boats server"
  policy      = data.aws_iam_policy_document.server_s3_access.json
}

resource "aws_route53_record" "site_a" {
  zone_id = data.aws_route53_zone.root.zone_id
  name    = local.site_fqdn
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = aws_cloudfront_distribution.site.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "site_aaaa" {
  zone_id = data.aws_route53_zone.root.zone_id
  name    = local.site_fqdn
  type    = "AAAA"

  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = aws_cloudfront_distribution.site.hosted_zone_id
    evaluate_target_health = false
  }
}
