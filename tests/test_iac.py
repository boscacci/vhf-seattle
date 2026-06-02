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
    variables_tf = Path("infra/opentofu/variables.tf").read_text(encoding="utf-8")

    assert 'resource "aws_s3_bucket_lifecycle_configuration" "raw_audio"' in main_tf
    assert 'prefix = "raw/"' in main_tf
    assert '"talkingboats-featured" = "false"' in main_tf
    assert "days = var.raw_retention_days" in main_tf
    assert 'default     = 90' in variables_tf
    assert "noncurrent_version_expiration" not in main_tf
    assert '"talkingboats-featured" = "true"' not in _lifecycle_block(main_tf)


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


def test_opentofu_tags_environment_boundaries() -> None:
    main_tf = Path("infra/opentofu/main.tf").read_text(encoding="utf-8")

    common_tags = _locals_block(main_tf)
    assert 'Application    = "elliott-bay-vhf"' in common_tags
    assert "BillingProject = var.project_name" in common_tags
    assert 'ManagedBy      = "opentofu"' in common_tags
    assert 'Owner          = "rob"' in common_tags
    assert "Project        = var.project_name" in common_tags

    assert 'Environment = "prod"' in _resource_block(main_tf, "aws_s3_bucket", "public_site")
    assert 'Environment = "prod"' in _resource_block(main_tf, "aws_s3_bucket", "raw_audio")
    assert 'Environment = "prod"' in _resource_block(
        main_tf, "aws_cloudfront_distribution", "site"
    )
    assert 'Environment = "dev"' in _resource_block(main_tf, "aws_s3_bucket", "dev_public_site")
    assert 'Environment = "dev"' in _resource_block(main_tf, "aws_s3_bucket", "dev_raw_audio")
    assert 'Environment = "dev"' in _resource_block(
        main_tf, "aws_cloudfront_distribution", "dev_site"
    )
    assert main_tf.count("merge(local.common_tags, {") >= 11


def test_opentofu_does_not_recreate_detached_server_iam_policies() -> None:
    main_tf = Path("infra/opentofu/main.tf").read_text(encoding="utf-8")
    outputs_tf = Path("infra/opentofu/outputs.tf").read_text(encoding="utf-8")

    assert 'resource "aws_iam_policy" "server_s3_access"' not in main_tf
    assert 'resource "aws_iam_policy" "dev_server_s3_access"' not in main_tf
    assert 'data "aws_iam_policy_document" "server_s3_access"' not in main_tf
    assert 'data "aws_iam_policy_document" "dev_server_s3_access"' not in main_tf
    assert 'output "server_iam_policy_arn"' not in outputs_tf
    assert 'output "dev_server_iam_policy_arn"' not in outputs_tf


def test_opentofu_defines_dynamodb_event_tables_for_dev_and_prod() -> None:
    main_tf = Path("infra/opentofu/main.tf").read_text(encoding="utf-8")
    outputs_tf = Path("infra/opentofu/outputs.tf").read_text(encoding="utf-8")

    prod_table = _resource_block(main_tf, "aws_dynamodb_table", "radio_events")
    dev_table = _resource_block(main_tf, "aws_dynamodb_table", "dev_radio_events")

    assert re.search(r'billing_mode\s+=\s+"PAY_PER_REQUEST"', prod_table)
    assert re.search(r'hash_key\s+=\s+"pk"', prod_table)
    assert re.search(r'range_key\s+=\s+"sk"', prod_table)
    assert re.search(r'stream_enabled\s+=\s+true', prod_table)
    assert "point_in_time_recovery" in prod_table
    assert 'Environment = "prod"' in prod_table

    assert re.search(r'billing_mode\s+=\s+"PAY_PER_REQUEST"', dev_table)
    assert re.search(r'hash_key\s+=\s+"pk"', dev_table)
    assert re.search(r'range_key\s+=\s+"sk"', dev_table)
    assert re.search(r'stream_enabled\s+=\s+true', dev_table)
    assert "point_in_time_recovery" in dev_table
    assert 'Environment = "dev"' in dev_table

    assert 'output "radio_events_table_name"' in outputs_tf
    assert 'output "dev_radio_events_table_name"' in outputs_tf


def test_public_site_deploy_script_enforces_branch_environment_hygiene() -> None:
    deploy_script = Path("scripts/deploy_public_site.sh").read_text(encoding="utf-8")

    assert "TALKINGBOATS_ALLOW_CROSS_ENV_DEPLOY" in deploy_script
    assert 'prod_expected_branch="main"' in deploy_script
    assert 'dev_allowed_branch_regex="^(dev|main|codex/.+|feature/.+)$"' in deploy_script
    assert 'if [[ "${branch}" == "unknown" ]]; then' in deploy_script
    assert "Refusing prod deploy from dirty worktree" in deploy_script
    assert "Refusing prod deploy from branch" in deploy_script


def test_deploy_script_uses_opentofu_cli_only() -> None:
    deploy_script = Path("scripts/deploy_public_site.sh").read_text(encoding="utf-8")

    assert 'tofu output -raw "${output_name}"' in deploy_script
    assert 'bucket="$(deploy_output_raw "${bucket_output}")"' in deploy_script
    assert 'distribution_id="$(deploy_output_raw "${distribution_output}")"' in deploy_script
    assert 'fqdn="$(deploy_output_raw "${fqdn_output}")"' in deploy_script
    assert "terraform " not in deploy_script.lower()


def test_cloudfront_routes_public_read_only_live_api_to_live_origin() -> None:
    main_tf = Path("infra/opentofu/main.tf").read_text(encoding="utf-8")
    variables_tf = Path("infra/opentofu/variables.tf").read_text(encoding="utf-8")

    assert 'variable "live_origin_domain_name"' in variables_tf
    assert 'default     = "optiplex.tailbea63b.ts.net"' in variables_tf
    assert 'variable "dev_tailnet_ipv4_addresses"' in variables_tf
    assert 'default     = ["100.124.5.39"]' in variables_tf
    assert 'variable "dev_tailnet_ipv6_addresses"' in variables_tf
    assert 'default     = ["fd7a:115c:a1e0::2601:597"]' in variables_tf
    assert 'resource "aws_cloudfront_origin_request_policy" "live_api"' in main_tf
    assert 'resource "aws_cloudfront_origin_request_policy" "operator_api"' not in main_tf
    assert 'query_string_behavior = "all"' in main_tf
    assert 'X-TalkingBoats-Operator-Token' not in main_tf
    assert 'origin_protocol_policy = "https-only"' in main_tf
    assert 'https_port             = var.live_origin_https_port' in main_tf
    assert 'path_pattern             = "/api/live/*"' in main_tf
    assert 'path_pattern             = "/api/clips/recent"' in main_tf
    assert 'path_pattern             = "/api/clips/search"' in main_tf
    assert 'path_pattern             = "/api/clips/playback"' in main_tf
    assert 'path_pattern             = "/api/clips/audio"' in main_tf
    assert 'path_pattern             = "/api/clips/corrections*"' not in main_tf
    assert 'path_pattern             = "/api/clips/features*"' not in main_tf
    assert 'path_pattern             = "/api/operator/session*"' not in main_tf
    assert 'path_pattern             = "/api/analysis/lexical"' in main_tf
    assert 'path_pattern             = "/ais-catcher/*"' in main_tf
    prod_distribution = _resource_block(main_tf, "aws_cloudfront_distribution", "site")
    dev_distribution = _resource_block(main_tf, "aws_cloudfront_distribution", "dev_site")
    dev_a_record = _resource_block(main_tf, "aws_route53_record", "dev_site_a")
    dev_aaaa_record = _resource_block(main_tf, "aws_route53_record", "dev_site_aaaa")
    assert 'path_pattern             = "/ais-catcher/*"' not in prod_distribution
    assert 'path_pattern             = "/ais-catcher/*"' in dev_distribution
    assert main_tf.count("target_origin_id         = local.live_origin_id") == 6
    assert 'path_pattern             = "/api/clips/corrections*"' not in prod_distribution
    assert 'path_pattern             = "/api/clips/features*"' not in prod_distribution
    assert 'path_pattern             = "/api/operator/session*"' not in prod_distribution
    assert 'path_pattern             = "/api/clips/corrections*"' not in dev_distribution
    assert 'path_pattern             = "/api/clips/features*"' not in dev_distribution
    assert 'path_pattern             = "/api/operator/session*"' not in dev_distribution
    assert 'enabled             = false' in dev_distribution
    assert main_tf.count("target_origin_id         = local.dev_live_origin_id") == 7
    assert "origin_request_policy_id = aws_cloudfront_origin_request_policy.live_api.id" in main_tf
    assert (
        "origin_request_policy_id = aws_cloudfront_origin_request_policy.operator_api.id"
        not in main_tf
    )
    assert "records = var.dev_tailnet_ipv4_addresses" in dev_a_record
    assert "records = var.dev_tailnet_ipv6_addresses" in dev_aaaa_record
    assert "alias {" not in dev_a_record
    assert "alias {" not in dev_aaaa_record


def test_opentofu_uses_static_certificate_validation_record_keys() -> None:
    main_tf = Path("infra/opentofu/main.tf").read_text(encoding="utf-8")

    prod_record = _resource_block(main_tf, "aws_route53_record", "site_cert_validation")
    dev_record = _resource_block(main_tf, "aws_route53_record", "dev_site_cert_validation")

    assert re.search(r"site_cert_validation_domains\s+=\s+toset\(\[local\.site_fqdn\]\)", main_tf)
    assert re.search(
        r"dev_site_cert_validation_domains\s+=\s+toset\(\[local\.dev_site_fqdn\]\)",
        main_tf,
    )
    assert "for_each = local.site_cert_validation_domains" in prod_record
    assert "for_each = local.dev_site_cert_validation_domains" in dev_record
    assert "if dvo.domain_name == each.value" in prod_record
    assert "if dvo.domain_name == each.value" in dev_record
    assert "dvo.domain_name =>" not in prod_record
    assert "dvo.domain_name =>" not in dev_record


def test_dev_cloudfront_marks_live_origin_requests_as_dev_only() -> None:
    main_tf = Path("infra/opentofu/main.tf").read_text(encoding="utf-8")
    prod_distribution = _resource_block(main_tf, "aws_cloudfront_distribution", "site")
    dev_distribution = _resource_block(main_tf, "aws_cloudfront_distribution", "dev_site")

    assert 'name  = "X-TalkingBoats-Environment"' in dev_distribution
    assert 'value = "dev"' in dev_distribution
    assert "X-TalkingBoats-Environment" not in prod_distribution


def test_dev_cognito_auth_allows_only_rob_as_super_admin() -> None:
    main_tf = Path("infra/opentofu/main.tf").read_text(encoding="utf-8")
    variables_tf = Path("infra/opentofu/variables.tf").read_text(encoding="utf-8")
    outputs_tf = Path("infra/opentofu/outputs.tf").read_text(encoding="utf-8")

    user_pool = _resource_block(main_tf, "aws_cognito_user_pool", "dev_auth")
    user = _resource_block(main_tf, "aws_cognito_user", "dev_super_admin")
    group = _resource_block(main_tf, "aws_cognito_user_group", "dev_super_admins")
    membership = _resource_block(main_tf, "aws_cognito_user_in_group", "dev_super_admin")
    client = _resource_block(main_tf, "aws_cognito_user_pool_client", "dev_mobile")

    assert 'variable "dev_admin_email"' in variables_tf
    assert 'default     = "cinemarob1@gmail.com"' in variables_tf
    assert "allow_admin_create_user_only = true" in user_pool
    assert 'username_attributes      = ["email"]' in user_pool
    assert re.search(r"username\s+=\s+var\.dev_admin_email", user)
    assert re.search(r"email\s+=\s+var\.dev_admin_email", user)
    assert re.search(r'name\s+=\s+"super-admins"', group)
    assert "aws_cognito_user.dev_super_admin.username" in membership
    assert 'allowed_oauth_flows_user_pool_client = true' in client
    assert 'allowed_oauth_flows                  = ["code"]' in client
    assert re.search(r"generate_secret\s+=\s+false", client)
    assert 'output "dev_cognito_user_pool_id"' in outputs_tf
    assert 'output "dev_cognito_mobile_client_id"' in outputs_tf
    assert 'output "dev_cognito_login_url"' in outputs_tf


def test_google_cognito_helper_uses_secret_manager_and_preserves_client_settings() -> None:
    configure_script = Path("scripts/configure_dev_google_cognito_idp.sh").read_text(
        encoding="utf-8"
    )

    assert "TALKINGBOATS_GOOGLE_OAUTH_SECRET_ID" in configure_script
    assert "aws secretsmanager get-secret-value" in configure_script
    assert "describe-user-pool-client" in configure_script
    assert "client_update_payload" in configure_script
    assert "CallbackURLs" in configure_script
    assert "AllowedOAuthFlows" in configure_script
    assert "--supported-identity-providers Google" not in configure_script


def _lifecycle_block(main_tf: str) -> str:
    start = main_tf.index('resource "aws_s3_bucket_lifecycle_configuration" "raw_audio"')
    end = main_tf.index('resource "aws_acm_certificate" "site"')
    return main_tf[start:end]


def _resource_block(main_tf: str, resource_type: str, resource_name: str) -> str:
    start = main_tf.index(f'resource "{resource_type}" "{resource_name}"')
    next_resource = main_tf.find('\nresource "', start + 1)
    next_data = main_tf.find('\ndata "', start + 1)
    candidates = [value for value in (next_resource, next_data) if value != -1]
    end = min(candidates) if candidates else len(main_tf)
    return main_tf[start:end]


def _locals_block(main_tf: str) -> str:
    start = main_tf.index("locals {")
    end = main_tf.index('\nresource "', start)
    return main_tf[start:end]
