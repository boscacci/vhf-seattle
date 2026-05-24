# Talking Boats OpenTofu Stack

This stack creates separate dev/prod static-site edges and private raw-audio buckets.

It intentionally does **not** create long-lived AWS access keys for the Raspberry
Pi. The Pi should ask the private API for presigned S3 upload URLs.

## Resources

- Prod private S3 bucket for public static-site files
- Dev private S3 bucket for public static-site files
- Separate dev/prod CloudFront distributions with Origin Access Control
- ACM certificates in `us-east-1`
- Route 53 `A` and `AAAA` aliases for:
  - `vhf.robertboscacci.com`
  - `vhf-dev.robertboscacci.com`
- Separate dev/prod private raw-audio S3 buckets with `raw/` lifecycle expiry
- Separate dev/prod IAM policies for the private server to presign audio,
  publish reviewed static files, and invalidate CloudFront

## Commands

```bash
tofu init
tofu fmt -recursive
tofu validate
tofu plan
```

Run `tofu apply` only after checking bucket names and AWS profile/account.

From the repo root, deploy static files with the helper:

```bash
scripts/deploy_public_site.sh dev outputs/public-site
scripts/deploy_public_site.sh prod outputs/public-site
```
