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

## Remote State

OpenTofu state is shared through an S3 backend so dev devices do not maintain
separate local state files:

- bucket: `talkingboats-opentofu-state-062008221187`
- key: `elliott-bay-vhf/opentofu.tfstate`
- region: `us-west-2`
- locking: native S3 lockfile with `use_lockfile = true`

The state bucket is a bootstrap dependency for this stack, not a resource
managed by the stack itself. Create or repair it idempotently before the first
`tofu init`:

```bash
aws s3api create-bucket \
  --bucket talkingboats-opentofu-state-062008221187 \
  --region us-west-2 \
  --create-bucket-configuration LocationConstraint=us-west-2

aws s3api put-public-access-block \
  --bucket talkingboats-opentofu-state-062008221187 \
  --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

aws s3api put-bucket-versioning \
  --bucket talkingboats-opentofu-state-062008221187 \
  --versioning-configuration Status=Enabled

aws s3api put-bucket-encryption \
  --bucket talkingboats-opentofu-state-062008221187 \
  --server-side-encryption-configuration \
    '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
```

Versioning is enabled so accidental state updates can be recovered from S3
object history. After changing an existing checkout from local state to S3,
migrate the current local state once:

```bash
tofu init -migrate-state -force-copy
tofu validate
```

On a fresh dev device, use plain `tofu init`; OpenTofu will read the shared S3
state. Do not commit `terraform.tfstate`, `terraform.tfstate.*`, or `.terraform/`
contents. Those local files are ignored and can be deleted after the migration
has been verified with `tofu state pull`.

From the repo root, deploy static files with the helper:

```bash
scripts/deploy_public_site.sh dev outputs/public-site
scripts/deploy_public_site.sh prod outputs/public-site
```

The deploy helper enforces branch hygiene:

- dev deploys: `dev`, `main`, `codex/*`, or `feature/*`
- prod deploys: clean `main` worktree only

See `docs/deployment-hygiene.md` for the full branch/resource policy.
