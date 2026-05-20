from pathlib import Path


def test_opentofu_keeps_public_and_raw_buckets_private() -> None:
    main_tf = Path("infra/opentofu/main.tf").read_text(encoding="utf-8")

    assert 'resource "aws_s3_bucket_public_access_block" "public_site"' in main_tf
    assert 'resource "aws_s3_bucket_public_access_block" "raw_audio"' in main_tf
    assert "block_public_policy     = true" in main_tf
    assert 'resource "aws_cloudfront_origin_access_control" "public_site"' in main_tf


def test_opentofu_expires_only_raw_audio_prefix() -> None:
    main_tf = Path("infra/opentofu/main.tf").read_text(encoding="utf-8")

    assert 'resource "aws_s3_bucket_lifecycle_configuration" "raw_audio"' in main_tf
    assert 'prefix = "raw/"' in main_tf
    assert "days = var.raw_retention_days" in main_tf
    assert "hall-of-fame" not in _lifecycle_block(main_tf)


def _lifecycle_block(main_tf: str) -> str:
    start = main_tf.index('resource "aws_s3_bucket_lifecycle_configuration" "raw_audio"')
    end = main_tf.index('resource "aws_acm_certificate" "site"')
    return main_tf[start:end]
