import re
from pathlib import Path


def test_opentofu_keeps_public_and_raw_buckets_private() -> None:
    main_tf = Path("infra/opentofu/main.tf").read_text(encoding="utf-8")

    assert 'resource "aws_s3_bucket_public_access_block" "public_site"' in main_tf
    assert 'resource "aws_s3_bucket_public_access_block" "raw_audio"' in main_tf
    assert 'resource "aws_s3_bucket_public_access_block" "dev_public_site"' in main_tf
    assert 'resource "aws_s3_bucket_public_access_block" "dev_raw_audio"' in main_tf
    assert "block_public_policy     = true" in main_tf
    assert 'resource "aws_cloudfront_origin_access_control" "public_site"' in main_tf
    assert 'resource "aws_cloudfront_origin_access_control" "dev_public_site"' in main_tf


def test_opentofu_expires_only_raw_audio_prefix() -> None:
    main_tf = Path("infra/opentofu/main.tf").read_text(encoding="utf-8")

    assert 'resource "aws_s3_bucket_lifecycle_configuration" "raw_audio"' in main_tf
    assert 'prefix = "raw/"' in main_tf
    assert "days = var.raw_retention_days" in main_tf
    assert "noncurrent_version_expiration" not in main_tf
    assert "hall-of-fame" not in _lifecycle_block(main_tf)


def test_opentofu_keeps_s3_bucket_versioning_suspended() -> None:
    main_tf = Path("infra/opentofu/main.tf").read_text(encoding="utf-8")

    assert main_tf.count('resource "aws_s3_bucket_versioning"') == 4
    versioning_blocks = [
        match.group(0)
        for match in re.finditer(
            r'resource "aws_s3_bucket_versioning" "[^"]+" \{.*?\n\}',
            main_tf,
            flags=re.DOTALL,
        )
    ]
    assert len(versioning_blocks) == 4
    assert all('status = "Suspended"' in block for block in versioning_blocks)
    assert all('status = "Enabled"' not in block for block in versioning_blocks)


def test_opentofu_has_distinct_dev_and_prod_outputs() -> None:
    outputs_tf = Path("infra/opentofu/outputs.tf").read_text(encoding="utf-8")
    variables_tf = Path("infra/opentofu/variables.tf").read_text(encoding="utf-8")

    assert 'default     = "vhf"' in variables_tf
    assert 'default     = "vhf-dev"' in variables_tf
    assert 'default     = "talkingboats"' in variables_tf
    assert 'default     = "dev.talkingboats"' in variables_tf
    assert "var.resource_site_subdomain" in Path("infra/opentofu/main.tf").read_text(
        encoding="utf-8"
    )
    assert 'output "site_fqdn"' in outputs_tf
    assert 'output "dev_site_fqdn"' in outputs_tf
    assert 'output "public_site_bucket"' in outputs_tf
    assert 'output "dev_public_site_bucket"' in outputs_tf


def test_cloudfront_routes_public_read_only_live_api_to_live_origin() -> None:
    main_tf = Path("infra/opentofu/main.tf").read_text(encoding="utf-8")
    variables_tf = Path("infra/opentofu/variables.tf").read_text(encoding="utf-8")

    assert 'variable "live_origin_domain_name"' in variables_tf
    assert 'default     = "optiplex.tailbea63b.ts.net"' in variables_tf
    assert 'resource "aws_cloudfront_origin_request_policy" "live_api"' in main_tf
    assert 'query_string_behavior = "all"' in main_tf
    assert 'origin_protocol_policy = "https-only"' in main_tf
    assert 'https_port             = var.live_origin_https_port' in main_tf
    assert 'path_pattern             = "/api/live/*"' in main_tf
    assert 'path_pattern             = "/api/clips/recent"' in main_tf
    assert main_tf.count("target_origin_id         = local.live_origin_id") == 2
    assert main_tf.count("target_origin_id         = local.dev_live_origin_id") == 2
    assert "origin_request_policy_id = aws_cloudfront_origin_request_policy.live_api.id" in main_tf


def _lifecycle_block(main_tf: str) -> str:
    start = main_tf.index('resource "aws_s3_bucket_lifecycle_configuration" "raw_audio"')
    end = main_tf.index('resource "aws_acm_certificate" "site"')
    return main_tf[start:end]
