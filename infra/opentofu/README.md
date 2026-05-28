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
- Explicit `Environment` tags on dev/prod buckets, CloudFront distributions,
  certificates, and server IAM policies
- Dev Cognito user pool for the mobile app. Sign-up is disabled, Rob is the only
  provisioned user, and the user is assigned to the `super-admins` group.

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

## Dev Mobile Auth

After `tofu apply`, generate the local Expo auth config:

```bash
scripts/write_mobile_auth_env.sh
```

The generated `mobile/.env.local` file is gitignored. The Cognito client is a
public PKCE client with no secret; never add provider secrets, temporary
passwords, or local token values to git.
