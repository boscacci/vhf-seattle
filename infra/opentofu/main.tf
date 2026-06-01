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
  site_fqdn            = "${var.site_subdomain}.${var.root_domain}"
  dev_site_fqdn        = "${var.dev_site_subdomain}.${var.root_domain}"
  bucket_base          = replace("${var.project_name}-${var.resource_site_subdomain}", ".", "-")
  dev_bucket_base      = replace("${var.project_name}-${var.dev_resource_site_subdomain}", ".", "-")
  public_bucket        = coalesce(var.public_site_bucket_name, "${local.bucket_base}-${data.aws_caller_identity.current.account_id}-public")
  raw_audio_bucket     = coalesce(var.raw_audio_bucket_name, "${local.bucket_base}-${data.aws_caller_identity.current.account_id}-raw")
  dev_public_bucket    = coalesce(var.dev_public_site_bucket_name, "${local.dev_bucket_base}-${data.aws_caller_identity.current.account_id}-public")
  dev_raw_audio_bucket = coalesce(var.dev_raw_audio_bucket_name, "${local.dev_bucket_base}-${data.aws_caller_identity.current.account_id}-raw")
  radio_events_table   = replace("${var.project_name}-${var.resource_site_subdomain}-events", ".", "-")
  dev_radio_events_table = replace(
    "${var.project_name}-${var.dev_resource_site_subdomain}-events",
    ".",
    "-",
  )
  site_cert_validation_domains     = toset([local.site_fqdn])
  dev_site_cert_validation_domains = toset([local.dev_site_fqdn])
  origin_id                        = "s3-public-site"
  dev_origin_id                    = "s3-dev-public-site"
  live_origin_id                   = "live-radio-proxy"
  dev_live_origin_id               = "dev-live-radio-proxy"
  dev_live_origin_domain_name = coalesce(
    var.dev_live_origin_domain_name,
    var.live_origin_domain_name,
  )
  dev_live_origin_https_port = coalesce(
    var.dev_live_origin_https_port,
    var.live_origin_https_port,
  )
  dev_cognito_domain_prefix = replace("${var.project_name}-${var.dev_resource_site_subdomain}-auth", ".", "-")
  dev_cognito_domain        = "https://${aws_cognito_user_pool_domain.dev_auth.domain}.auth.${var.aws_region}.amazoncognito.com"
  common_tags = {
    Application    = "elliott-bay-vhf"
    BillingProject = var.project_name
    ManagedBy      = "opentofu"
    Owner          = "rob"
    Project        = var.project_name
  }
}

resource "aws_s3_bucket" "public_site" {
  bucket        = local.public_bucket
  force_destroy = var.force_destroy_buckets

  tags = merge(local.common_tags, {
    Environment = "prod"
    Role        = "public-static-site"
  })
}

resource "aws_s3_bucket" "raw_audio" {
  bucket        = local.raw_audio_bucket
  force_destroy = var.force_destroy_buckets

  tags = merge(local.common_tags, {
    Environment = "prod"
    Role        = "private-raw-audio"
  })
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
    status = "Suspended"
  }
}

resource "aws_s3_bucket_versioning" "raw_audio" {
  bucket = aws_s3_bucket.raw_audio.id

  versioning_configuration {
    status = "Suspended"
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

  }
}

resource "aws_dynamodb_table" "radio_events" {
  name             = local.radio_events_table
  billing_mode     = "PAY_PER_REQUEST"
  hash_key         = "pk"
  range_key        = "sk"
  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  tags = merge(local.common_tags, {
    Environment = "prod"
    Role        = "radio-event-store"
  })
}

resource "aws_acm_certificate" "site" {
  provider          = aws.us_east_1
  domain_name       = local.site_fqdn
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = merge(local.common_tags, {
    Environment = "prod"
    Role        = "tls-certificate"
  })
}

resource "aws_route53_record" "site_cert_validation" {
  for_each = local.site_cert_validation_domains

  zone_id = data.aws_route53_zone.root.zone_id
  name = one([
    for dvo in aws_acm_certificate.site.domain_validation_options : dvo.resource_record_name
    if dvo.domain_name == each.value
  ])
  type = one([
    for dvo in aws_acm_certificate.site.domain_validation_options : dvo.resource_record_type
    if dvo.domain_name == each.value
  ])
  ttl = 60
  records = [
    one([
      for dvo in aws_acm_certificate.site.domain_validation_options : dvo.resource_record_value
      if dvo.domain_name == each.value
    ])
  ]

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

resource "aws_cloudfront_origin_request_policy" "live_api" {
  name    = "${var.project_name}-live-api-origin-request"
  comment = "Forward query strings to the read-only Elliott Bay VHF live API origin"

  cookies_config {
    cookie_behavior = "none"
  }

  headers_config {
    header_behavior = "none"
  }

  query_strings_config {
    query_string_behavior = "all"
  }
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

  origin {
    domain_name = var.live_origin_domain_name
    origin_id   = local.live_origin_id

    custom_origin_config {
      http_port              = 80
      https_port             = var.live_origin_https_port
      origin_protocol_policy = "https-only"
      origin_read_timeout    = 60
      origin_ssl_protocols   = ["TLSv1.2"]
    }
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
    path_pattern             = "/api/live/*"
    target_origin_id         = local.live_origin_id
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = false
    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id = aws_cloudfront_origin_request_policy.live_api.id
  }

  ordered_cache_behavior {
    path_pattern             = "/api/clips/recent"
    target_origin_id         = local.live_origin_id
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = true
    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id = aws_cloudfront_origin_request_policy.live_api.id
  }

  ordered_cache_behavior {
    path_pattern             = "/api/clips/search"
    target_origin_id         = local.live_origin_id
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = true
    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id = aws_cloudfront_origin_request_policy.live_api.id
  }

  ordered_cache_behavior {
    path_pattern             = "/api/clips/playback"
    target_origin_id         = local.live_origin_id
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = true
    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id = aws_cloudfront_origin_request_policy.live_api.id
  }

  ordered_cache_behavior {
    path_pattern             = "/api/clips/audio"
    target_origin_id         = local.live_origin_id
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = false
    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id = aws_cloudfront_origin_request_policy.live_api.id
  }

  ordered_cache_behavior {
    path_pattern             = "/api/analysis/lexical"
    target_origin_id         = local.live_origin_id
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = true
    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id = aws_cloudfront_origin_request_policy.live_api.id
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

  tags = merge(local.common_tags, {
    Environment = "prod"
    Role        = "public-static-site"
  })

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

resource "aws_s3_bucket" "dev_public_site" {
  bucket        = local.dev_public_bucket
  force_destroy = var.force_destroy_buckets

  tags = merge(local.common_tags, {
    Environment = "dev"
    Role        = "public-static-site"
  })
}

resource "aws_s3_bucket" "dev_raw_audio" {
  bucket        = local.dev_raw_audio_bucket
  force_destroy = var.force_destroy_buckets

  tags = merge(local.common_tags, {
    Environment = "dev"
    Role        = "private-raw-audio"
  })
}

resource "aws_s3_bucket_public_access_block" "dev_public_site" {
  bucket                  = aws_s3_bucket.dev_public_site.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_public_access_block" "dev_raw_audio" {
  bucket                  = aws_s3_bucket.dev_raw_audio.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "dev_public_site" {
  bucket = aws_s3_bucket.dev_public_site.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "dev_raw_audio" {
  bucket = aws_s3_bucket.dev_raw_audio.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "dev_public_site" {
  bucket = aws_s3_bucket.dev_public_site.id

  versioning_configuration {
    status = "Suspended"
  }
}

resource "aws_s3_bucket_versioning" "dev_raw_audio" {
  bucket = aws_s3_bucket.dev_raw_audio.id

  versioning_configuration {
    status = "Suspended"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "dev_raw_audio" {
  bucket = aws_s3_bucket.dev_raw_audio.id

  rule {
    id     = "expire-raw-audio"
    status = "Enabled"

    filter {
      prefix = "raw/"
    }

    expiration {
      days = var.raw_retention_days
    }

  }
}

resource "aws_dynamodb_table" "dev_radio_events" {
  name             = local.dev_radio_events_table
  billing_mode     = "PAY_PER_REQUEST"
  hash_key         = "pk"
  range_key        = "sk"
  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  tags = merge(local.common_tags, {
    Environment = "dev"
    Role        = "radio-event-store"
  })
}

resource "aws_acm_certificate" "dev_site" {
  provider          = aws.us_east_1
  domain_name       = local.dev_site_fqdn
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = merge(local.common_tags, {
    Environment = "dev"
    Role        = "tls-certificate"
  })
}

resource "aws_route53_record" "dev_site_cert_validation" {
  for_each = local.dev_site_cert_validation_domains

  zone_id = data.aws_route53_zone.root.zone_id
  name = one([
    for dvo in aws_acm_certificate.dev_site.domain_validation_options : dvo.resource_record_name
    if dvo.domain_name == each.value
  ])
  type = one([
    for dvo in aws_acm_certificate.dev_site.domain_validation_options : dvo.resource_record_type
    if dvo.domain_name == each.value
  ])
  ttl = 60
  records = [
    one([
      for dvo in aws_acm_certificate.dev_site.domain_validation_options : dvo.resource_record_value
      if dvo.domain_name == each.value
    ])
  ]

  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "dev_site" {
  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.dev_site.arn
  validation_record_fqdns = [for record in aws_route53_record.dev_site_cert_validation : record.fqdn]
}

resource "aws_cloudfront_origin_access_control" "dev_public_site" {
  name                              = "${local.dev_site_fqdn}-s3-oac"
  description                       = "CloudFront-only access to the Talking Boats dev static site bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "dev_site" {
  enabled             = false
  comment             = "Disabled legacy Talking Boats dev CloudFront distribution; dev DNS is tailnet-only"
  aliases             = [local.dev_site_fqdn]
  default_root_object = "index.html"
  is_ipv6_enabled     = true
  price_class         = "PriceClass_100"

  origin {
    domain_name              = aws_s3_bucket.dev_public_site.bucket_regional_domain_name
    origin_id                = local.dev_origin_id
    origin_access_control_id = aws_cloudfront_origin_access_control.dev_public_site.id
  }

  origin {
    domain_name = local.dev_live_origin_domain_name
    origin_id   = local.dev_live_origin_id

    custom_header {
      name  = "X-TalkingBoats-Environment"
      value = "dev"
    }

    custom_origin_config {
      http_port              = 80
      https_port             = local.dev_live_origin_https_port
      origin_protocol_policy = "https-only"
      origin_read_timeout    = 60
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id       = local.dev_origin_id
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    cache_policy_id        = data.aws_cloudfront_cache_policy.caching_optimized.id
  }

  ordered_cache_behavior {
    path_pattern             = "/api/live/*"
    target_origin_id         = local.dev_live_origin_id
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = false
    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id = aws_cloudfront_origin_request_policy.live_api.id
  }

  ordered_cache_behavior {
    path_pattern             = "/api/clips/recent"
    target_origin_id         = local.dev_live_origin_id
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = true
    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id = aws_cloudfront_origin_request_policy.live_api.id
  }

  ordered_cache_behavior {
    path_pattern             = "/api/clips/search"
    target_origin_id         = local.dev_live_origin_id
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = true
    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id = aws_cloudfront_origin_request_policy.live_api.id
  }

  ordered_cache_behavior {
    path_pattern             = "/api/clips/playback"
    target_origin_id         = local.dev_live_origin_id
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = true
    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id = aws_cloudfront_origin_request_policy.live_api.id
  }

  ordered_cache_behavior {
    path_pattern             = "/api/clips/audio"
    target_origin_id         = local.dev_live_origin_id
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = false
    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id = aws_cloudfront_origin_request_policy.live_api.id
  }

  ordered_cache_behavior {
    path_pattern             = "/api/analysis/lexical"
    target_origin_id         = local.dev_live_origin_id
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = true
    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id = aws_cloudfront_origin_request_policy.live_api.id
  }

  ordered_cache_behavior {
    path_pattern             = "/ais-catcher/*"
    target_origin_id         = local.dev_live_origin_id
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = true
    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id = aws_cloudfront_origin_request_policy.live_api.id
  }

  ordered_cache_behavior {
    path_pattern           = "public_manifest.json"
    target_origin_id       = local.dev_origin_id
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
    acm_certificate_arn      = aws_acm_certificate_validation.dev_site.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  tags = merge(local.common_tags, {
    Environment = "dev"
    Role        = "public-static-site"
  })

  depends_on = [aws_acm_certificate_validation.dev_site]
}

data "aws_iam_policy_document" "dev_public_site_cloudfront_read" {
  statement {
    sid     = "AllowCloudFrontRead"
    actions = ["s3:GetObject"]

    resources = ["${aws_s3_bucket.dev_public_site.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.dev_site.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "dev_public_site" {
  bucket = aws_s3_bucket.dev_public_site.id
  policy = data.aws_iam_policy_document.dev_public_site_cloudfront_read.json
}

resource "aws_route53_record" "dev_site_a" {
  zone_id = data.aws_route53_zone.root.zone_id
  name    = local.dev_site_fqdn
  type    = "A"
  ttl     = 300
  records = var.dev_tailnet_ipv4_addresses
}

resource "aws_route53_record" "dev_site_aaaa" {
  zone_id = data.aws_route53_zone.root.zone_id
  name    = local.dev_site_fqdn
  type    = "AAAA"
  ttl     = 300
  records = var.dev_tailnet_ipv6_addresses
}

resource "aws_cognito_user_pool" "dev_auth" {
  name                     = "${var.project_name}-dev-auth"
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  deletion_protection      = "ACTIVE"
  user_pool_tier           = "ESSENTIALS"

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  password_policy {
    minimum_length                   = 14
    password_history_size            = 5
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = true
    require_uppercase                = true
    temporary_password_validity_days = 7
  }

  schema {
    attribute_data_type = "String"
    mutable             = true
    name                = "email"
    required            = true

    string_attribute_constraints {
      min_length = "5"
      max_length = "2048"
    }
  }

  sign_in_policy {
    allowed_first_auth_factors = ["PASSWORD"]
  }

  web_authn_configuration {
    relying_party_id  = local.dev_site_fqdn
    user_verification = "required"
  }

  tags = merge(local.common_tags, {
    Environment = "dev"
    Role        = "mobile-auth"
  })
}

resource "aws_cognito_user_pool_domain" "dev_auth" {
  domain                = local.dev_cognito_domain_prefix
  managed_login_version = 2
  user_pool_id          = aws_cognito_user_pool.dev_auth.id
}

resource "aws_cognito_user_pool_client" "dev_mobile" {
  name                                 = "${var.project_name}-dev-mobile"
  user_pool_id                         = aws_cognito_user_pool.dev_auth.id
  generate_secret                      = false
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["email", "openid", "profile"]
  callback_urls                        = var.dev_auth_callback_urls
  logout_urls                          = var.dev_auth_logout_urls
  supported_identity_providers         = ["COGNITO"]
  prevent_user_existence_errors        = "ENABLED"
  enable_token_revocation              = true
  access_token_validity                = 1
  id_token_validity                    = 1
  refresh_token_validity               = 30

  explicit_auth_flows = [
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_SRP_AUTH",
  ]

  read_attributes = [
    "email",
    "email_verified",
  ]

  write_attributes = [
    "email",
  ]

  lifecycle {
    ignore_changes = [supported_identity_providers]
  }
}

resource "aws_cognito_managed_login_branding" "dev_mobile" {
  client_id                   = aws_cognito_user_pool_client.dev_mobile.id
  user_pool_id                = aws_cognito_user_pool.dev_auth.id
  use_cognito_provided_values = true

  depends_on = [aws_cognito_user_pool_domain.dev_auth]
}

resource "aws_cognito_user_group" "dev_super_admins" {
  name         = "super-admins"
  description  = "Full administrative access to the Elliott Bay VHF dev app"
  precedence   = 0
  user_pool_id = aws_cognito_user_pool.dev_auth.id
}

resource "aws_cognito_user" "dev_super_admin" {
  user_pool_id             = aws_cognito_user_pool.dev_auth.id
  username                 = var.dev_admin_email
  desired_delivery_mediums = ["EMAIL"]
  force_alias_creation     = false

  attributes = {
    email          = var.dev_admin_email
    email_verified = "true"
  }
}

resource "aws_cognito_user_in_group" "dev_super_admin" {
  group_name   = aws_cognito_user_group.dev_super_admins.name
  user_pool_id = aws_cognito_user_pool.dev_auth.id
  username     = aws_cognito_user.dev_super_admin.username
}
