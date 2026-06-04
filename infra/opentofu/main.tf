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

data "archive_file" "ais_lambda" {
  type        = "zip"
  output_path = "${path.module}/.terraform/talkingboats-ais-live.zip"

  source {
    filename = "talkingboats/__init__.py"
    content  = file("${path.module}/../../src/talkingboats/__init__.py")
  }

  source {
    filename = "talkingboats/ais_history.py"
    content  = file("${path.module}/../../src/talkingboats/ais_history.py")
  }

  source {
    filename = "talkingboats/ais_live.py"
    content  = file("${path.module}/../../src/talkingboats/ais_live.py")
  }
}

locals {
  site_fqdn            = "${var.site_subdomain}.${var.root_domain}"
  dev_site_fqdn        = "${var.dev_site_subdomain}.${var.root_domain}"
  ais_live_fqdn        = "${var.ais_live_subdomain}.${var.root_domain}"
  bucket_base          = replace("${var.project_name}-${var.resource_site_subdomain}", ".", "-")
  dev_bucket_base      = replace("${var.project_name}-${var.dev_resource_site_subdomain}", ".", "-")
  public_bucket        = coalesce(var.public_site_bucket_name, "${local.bucket_base}-${data.aws_caller_identity.current.account_id}-public")
  raw_audio_bucket     = coalesce(var.raw_audio_bucket_name, "${local.bucket_base}-${data.aws_caller_identity.current.account_id}-raw")
  dev_public_bucket    = coalesce(var.dev_public_site_bucket_name, "${local.dev_bucket_base}-${data.aws_caller_identity.current.account_id}-public")
  dev_raw_audio_bucket = coalesce(var.dev_raw_audio_bucket_name, "${local.dev_bucket_base}-${data.aws_caller_identity.current.account_id}-raw")
  radio_events_table   = replace("${var.project_name}-${var.resource_site_subdomain}-events", ".", "-")
  ais_connections_table = replace(
    "${var.project_name}-${var.resource_site_subdomain}-ais-connections",
    ".",
    "-",
  )
  ais_ingest_secret_name = replace(
    "${var.project_name}-${var.resource_site_subdomain}-ais-ingest-token",
    ".",
    "-",
  )
  dev_radio_events_table = replace(
    "${var.project_name}-${var.dev_resource_site_subdomain}-events",
    ".",
    "-",
  )
  ais_lambda_name                  = replace("${var.project_name}-${var.resource_site_subdomain}-ais-ingest", ".", "-")
  ais_websocket_lambda_name        = replace("${var.project_name}-${var.resource_site_subdomain}-ais-websocket", ".", "-")
  site_cert_validation_domains     = toset([local.site_fqdn])
  dev_site_cert_validation_domains = toset([local.dev_site_fqdn])
  ais_live_cert_validation_domains = toset([local.ais_live_fqdn])
  origin_id                        = "s3-public-site"
  dev_origin_id                    = "s3-dev-public-site"
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
      and {
        prefix = "raw/"
        tags = {
          "talkingboats-featured" = "false"
        }
      }
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

resource "aws_dynamodb_table" "ais_connections" {
  name         = local.ais_connections_table
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "connection_id"

  attribute {
    name = "connection_id"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  server_side_encryption {
    enabled = true
  }

  tags = merge(local.common_tags, {
    Environment = "prod"
    Role        = "ais-websocket-connections"
  })
}

resource "aws_kms_key" "ais_ingest_secret" {
  description             = "Encrypt the Talking Boats AIS ingest token in Secrets Manager"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = merge(local.common_tags, {
    Environment = "prod"
    Role        = "ais-ingest-secret-kms"
  })
}

resource "aws_kms_alias" "ais_ingest_secret" {
  name          = "alias/${local.ais_ingest_secret_name}"
  target_key_id = aws_kms_key.ais_ingest_secret.key_id
}

resource "aws_secretsmanager_secret" "ais_ingest_token" {
  name                    = local.ais_ingest_secret_name
  description             = "Raw AIS ingest token for the Raspberry Pi forwarder"
  kms_key_id              = aws_kms_key.ais_ingest_secret.arn
  recovery_window_in_days = 7

  tags = merge(local.common_tags, {
    Environment = "prod"
    Role        = "ais-ingest-token"
  })
}

data "aws_iam_policy_document" "ais_lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ais_lambda" {
  name               = replace("${var.project_name}-${var.resource_site_subdomain}-ais-lambda", ".", "-")
  assume_role_policy = data.aws_iam_policy_document.ais_lambda_assume_role.json

  tags = merge(local.common_tags, {
    Environment = "prod"
    Role        = "ais-lambda"
  })
}

resource "aws_iam_role_policy_attachment" "ais_lambda_basic_execution" {
  role       = aws_iam_role.ais_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "ais_lambda_access" {
  statement {
    sid       = "WritePublicAisSnapshot"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.public_site.arn}/ais/latest.json"]
  }

  statement {
    sid = "TrackWebsocketConnections"
    actions = [
      "dynamodb:DeleteItem",
      "dynamodb:PutItem",
      "dynamodb:Scan",
    ]
    resources = [aws_dynamodb_table.ais_connections.arn]
  }

  statement {
    sid     = "FanOutAisSnapshots"
    actions = ["execute-api:ManageConnections"]
    resources = [
      "arn:aws:execute-api:${var.aws_region}:${data.aws_caller_identity.current.account_id}:${aws_apigatewayv2_api.ais_websocket.id}/*/POST/@connections/*",
    ]
  }
}

resource "aws_iam_role_policy" "ais_lambda_access" {
  name   = replace("${var.project_name}-${var.resource_site_subdomain}-ais-lambda-access", ".", "-")
  role   = aws_iam_role.ais_lambda.id
  policy = data.aws_iam_policy_document.ais_lambda_access.json
}

resource "aws_cloudwatch_log_group" "ais_ingest" {
  name              = "/aws/lambda/${local.ais_lambda_name}"
  retention_in_days = 30

  tags = merge(local.common_tags, {
    Environment = "prod"
    Role        = "ais-ingest-logs"
  })
}

resource "aws_cloudwatch_log_group" "ais_websocket" {
  name              = "/aws/lambda/${local.ais_websocket_lambda_name}"
  retention_in_days = 30

  tags = merge(local.common_tags, {
    Environment = "prod"
    Role        = "ais-websocket-logs"
  })
}

resource "aws_lambda_function" "ais_ingest" {
  function_name    = local.ais_lambda_name
  role             = aws_iam_role.ais_lambda.arn
  filename         = data.archive_file.ais_lambda.output_path
  source_code_hash = data.archive_file.ais_lambda.output_base64sha256
  runtime          = "python3.12"
  handler          = "talkingboats.ais_live.ais_lambda_handler"
  timeout          = 10
  memory_size      = 256

  environment {
    variables = {
      TALKINGBOATS_AIS_CONNECTIONS_TABLE   = aws_dynamodb_table.ais_connections.name
      TALKINGBOATS_AIS_INGEST_TOKEN_SHA256 = var.ais_ingest_token_sha256
      TALKINGBOATS_AIS_SNAPSHOT_BUCKET     = aws_s3_bucket.public_site.bucket
      TALKINGBOATS_AIS_SNAPSHOT_KEY        = "ais/latest.json"
      TALKINGBOATS_AIS_STATION             = "Elliott Bay VHF"
      TALKINGBOATS_AIS_WEBSOCKET_ENDPOINT  = "${replace(aws_apigatewayv2_api.ais_websocket.api_endpoint, "wss://", "https://")}/${aws_apigatewayv2_stage.ais_websocket.name}"
    }
  }

  tags = merge(local.common_tags, {
    Environment = "prod"
    Role        = "ais-ingest"
  })

  depends_on = [
    aws_cloudwatch_log_group.ais_ingest,
    aws_iam_role_policy_attachment.ais_lambda_basic_execution,
    aws_iam_role_policy.ais_lambda_access,
  ]
}

resource "aws_lambda_function" "ais_websocket" {
  function_name    = local.ais_websocket_lambda_name
  role             = aws_iam_role.ais_lambda.arn
  filename         = data.archive_file.ais_lambda.output_path
  source_code_hash = data.archive_file.ais_lambda.output_base64sha256
  runtime          = "python3.12"
  handler          = "talkingboats.ais_live.ais_websocket_handler"
  timeout          = 10
  memory_size      = 256

  environment {
    variables = {
      TALKINGBOATS_AIS_CONNECTIONS_TABLE      = aws_dynamodb_table.ais_connections.name
      TALKINGBOATS_AIS_CONNECTION_TTL_SECONDS = "3600"
    }
  }

  tags = merge(local.common_tags, {
    Environment = "prod"
    Role        = "ais-websocket"
  })

  depends_on = [
    aws_cloudwatch_log_group.ais_websocket,
    aws_iam_role_policy_attachment.ais_lambda_basic_execution,
    aws_iam_role_policy.ais_lambda_access,
  ]
}

resource "aws_apigatewayv2_api" "ais_http" {
  name          = replace("${var.project_name}-${var.resource_site_subdomain}-ais-http", ".", "-")
  protocol_type = "HTTP"

  tags = merge(local.common_tags, {
    Environment = "prod"
    Role        = "ais-http-ingest"
  })
}

resource "aws_apigatewayv2_integration" "ais_http" {
  api_id                 = aws_apigatewayv2_api.ais_http.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.ais_ingest.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "ais_http_ingest" {
  api_id    = aws_apigatewayv2_api.ais_http.id
  route_key = "POST /ais"
  target    = "integrations/${aws_apigatewayv2_integration.ais_http.id}"
}

resource "aws_apigatewayv2_stage" "ais_http" {
  api_id      = aws_apigatewayv2_api.ais_http.id
  name        = "$default"
  auto_deploy = true

  tags = merge(local.common_tags, {
    Environment = "prod"
    Role        = "ais-http-ingest-stage"
  })
}

resource "aws_lambda_permission" "ais_http" {
  statement_id  = "AllowAisHttpInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ais_ingest.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.ais_http.execution_arn}/*/*/ais"
}

resource "aws_apigatewayv2_api" "ais_websocket" {
  name                       = replace("${var.project_name}-${var.resource_site_subdomain}-ais-websocket", ".", "-")
  protocol_type              = "WEBSOCKET"
  route_selection_expression = "$request.body.action"

  tags = merge(local.common_tags, {
    Environment = "prod"
    Role        = "ais-public-websocket"
  })
}

resource "aws_apigatewayv2_integration" "ais_websocket" {
  api_id           = aws_apigatewayv2_api.ais_websocket.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.ais_websocket.invoke_arn
}

resource "aws_apigatewayv2_route" "ais_websocket_connect" {
  api_id    = aws_apigatewayv2_api.ais_websocket.id
  route_key = "$connect"
  target    = "integrations/${aws_apigatewayv2_integration.ais_websocket.id}"
}

resource "aws_apigatewayv2_route" "ais_websocket_disconnect" {
  api_id    = aws_apigatewayv2_api.ais_websocket.id
  route_key = "$disconnect"
  target    = "integrations/${aws_apigatewayv2_integration.ais_websocket.id}"
}

resource "aws_apigatewayv2_route" "ais_websocket_default" {
  api_id    = aws_apigatewayv2_api.ais_websocket.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.ais_websocket.id}"
}

resource "aws_apigatewayv2_stage" "ais_websocket" {
  api_id      = aws_apigatewayv2_api.ais_websocket.id
  name        = "v1"
  auto_deploy = true

  tags = merge(local.common_tags, {
    Environment = "prod"
    Role        = "ais-public-websocket-stage"
  })
}

resource "aws_lambda_permission" "ais_websocket" {
  statement_id  = "AllowAisWebsocketInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ais_websocket.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.ais_websocket.execution_arn}/*"
}

resource "aws_acm_certificate" "ais_live" {
  domain_name       = local.ais_live_fqdn
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = merge(local.common_tags, {
    Environment = "prod"
    Role        = "ais-live-tls-certificate"
  })
}

resource "aws_route53_record" "ais_live_cert_validation" {
  for_each = local.ais_live_cert_validation_domains

  zone_id = data.aws_route53_zone.root.zone_id
  name = one([
    for dvo in aws_acm_certificate.ais_live.domain_validation_options : dvo.resource_record_name
    if dvo.domain_name == each.value
  ])
  type = one([
    for dvo in aws_acm_certificate.ais_live.domain_validation_options : dvo.resource_record_type
    if dvo.domain_name == each.value
  ])
  ttl = 60
  records = [
    one([
      for dvo in aws_acm_certificate.ais_live.domain_validation_options : dvo.resource_record_value
      if dvo.domain_name == each.value
    ])
  ]

  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "ais_live" {
  certificate_arn         = aws_acm_certificate.ais_live.arn
  validation_record_fqdns = [for record in aws_route53_record.ais_live_cert_validation : record.fqdn]
}

resource "aws_apigatewayv2_domain_name" "ais_live" {
  domain_name = local.ais_live_fqdn

  domain_name_configuration {
    certificate_arn = aws_acm_certificate_validation.ais_live.certificate_arn
    endpoint_type   = "REGIONAL"
    security_policy = "TLS_1_2"
  }

  tags = merge(local.common_tags, {
    Environment = "prod"
    Role        = "ais-live-websocket-domain"
  })
}

resource "aws_apigatewayv2_api_mapping" "ais_websocket" {
  api_id          = aws_apigatewayv2_api.ais_websocket.id
  domain_name     = aws_apigatewayv2_domain_name.ais_live.id
  stage           = aws_apigatewayv2_stage.ais_websocket.name
  api_mapping_key = "v1"
}

resource "aws_route53_record" "ais_live_a" {
  zone_id = data.aws_route53_zone.root.zone_id
  name    = local.ais_live_fqdn
  type    = "A"

  alias {
    name                   = aws_apigatewayv2_domain_name.ais_live.domain_name_configuration[0].target_domain_name
    zone_id                = aws_apigatewayv2_domain_name.ais_live.domain_name_configuration[0].hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "ais_live_aaaa" {
  zone_id = data.aws_route53_zone.root.zone_id
  name    = local.ais_live_fqdn
  type    = "AAAA"

  alias {
    name                   = aws_apigatewayv2_domain_name.ais_live.domain_name_configuration[0].target_domain_name
    zone_id                = aws_apigatewayv2_domain_name.ais_live.domain_name_configuration[0].hosted_zone_id
    evaluate_target_health = false
  }
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
      and {
        prefix = "raw/"
        tags = {
          "talkingboats-featured" = "false"
        }
      }
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

  default_cache_behavior {
    target_origin_id       = local.dev_origin_id
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    cache_policy_id        = data.aws_cloudfront_cache_policy.caching_optimized.id
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
