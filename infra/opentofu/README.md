# Talking Boats OpenTofu Stack

This stack creates separate dev/prod static-site storage and private raw-audio buckets.

It intentionally does **not** create long-lived AWS access keys for the Raspberry
Pi. The Pi should ask the private API for presigned S3 upload URLs.

## Resources

- Prod private S3 bucket for public static-site files
- Dev private S3 bucket for public static-site files
- Prod CloudFront distribution with Origin Access Control
- Disabled legacy dev CloudFront distribution retained for controlled teardown
- ACM certificates in `us-east-1`
- Route 53 `A` and `AAAA` records for:
  - `vhf.robertboscacci.com` as CloudFront aliases
  - `vhf-dev.robertboscacci.com` as tailnet address records
- Separate dev/prod private raw-audio S3 buckets with tag-filtered `raw/`
  lifecycle expiry: unstarred clips expire after 90 days, starred clips are
  retained
- Separate dev/prod IAM policies for the private server to presign audio,
  publish reviewed static files, and invalidate CloudFront
- Explicit `Environment` tags on dev/prod buckets, CloudFront distributions,
  certificates, and server IAM policies

## Commands

Use OpenTofu only. Do not install or run HashiCorp Terraform for this repo.

```bash
tofu init
tofu fmt -recursive
tofu validate
tofu plan
```

OpenTofu still uses the HCL `terraform { ... }` settings block and the
`.terraform.lock.hcl` dependency lock filename for compatibility. Those names do
not mean the Terraform CLI is required.

Run `tofu apply` only after checking bucket names and AWS profile/account.

From the repo root, deploy static files with the helper:

```bash
scripts/deploy_public_site.sh dev outputs/public-site
scripts/deploy_public_site.sh prod outputs/public-site
```

The deploy helper enforces branch hygiene:

- dev deploys: `dev`, `main`, `codex/*`, or `feature/*`
- prod deploys: clean `main` worktree only

See `docs/deployment-hygiene.md` for the full branch/resource policy.
