# Deployment Hygiene

This project has separate dev and prod public edges. Keep the code flow and the
AWS resources separate unless an emergency override is intentional and recorded.

## Branch Policy

- `dev`: integration branch for `https://vhf-dev.robertboscacci.com`. Use this
  for normal validation before promotion. Short-lived `codex/*` or `feature/*`
  branches may deploy to dev while a change is being tested.
- `main`: production branch for `https://vhf.robertboscacci.com`. Prod deploys
  should come from `main` only, after dev has been smoke tested.

First-time branch setup, if the remote only has `main`:

```bash
git fetch origin
git switch -c dev origin/main
git push -u origin dev
```

Normal flow:

```bash
git switch dev
git merge --ff-only codex/my-change
scripts/deploy_public_site.sh dev outputs/public-site

git switch main
git merge --ff-only dev
scripts/deploy_public_site.sh prod outputs/public-site
```

The deploy helper enforces the branch policy by default. It allows dev deploys
from `dev`, `main`, `codex/*`, or `feature/*`, and allows prod deploys only from
`main` with a clean worktree. For a deliberate emergency, set
`TALKINGBOATS_ALLOW_CROSS_ENV_DEPLOY=1` and record why in the operator notes.

## Resource Policy

OpenTofu owns durable AWS resources in `infra/opentofu`.
Use the `tofu` CLI only; this repo should not depend on the HashiCorp Terraform
CLI. The HCL `terraform { ... }` block and `.terraform.lock.hcl` filename remain
because OpenTofu intentionally keeps those compatibility points.

| Concern | Dev | Prod |
| --- | --- | --- |
| Branch | `dev`, `codex/*`, `feature/*` | `main` |
| Public hostname | `vhf-dev.robertboscacci.com` | `vhf.robertboscacci.com` |
| Static origin | `dev_public_site_bucket` output | `public_site_bucket` output |
| Raw audio | `dev_raw_audio_bucket` output | `raw_audio_bucket` output |
| CloudFront | `dev_cloudfront_distribution_id` output | `cloudfront_distribution_id` output |
| IAM policy | `dev_server_iam_policy_arn` output | `server_iam_policy_arn` output |

Dev and prod buckets, distributions, certificates, and server IAM policies carry
explicit `Environment` tags. Public buckets stay private and are readable only
through their matching CloudFront Origin Access Control.

The dev CloudFront distribution may share the same read-only OptiPlex live
origin as prod unless `dev_live_origin_domain_name` is set. That is acceptable
for live listening because the public routes are read-only. It is not permission
for dev workers to write to prod raw or public buckets.

## Operator Checklist

Before dev deploy:

- Confirm the target is `dev`.
- Confirm the branch is `dev`, `main`, `codex/*`, or `feature/*`.
- Run the relevant tests for the changed area.
- Smoke `https://vhf-dev.robertboscacci.com`.

Before prod deploy:

- Merge the tested dev change into `main`.
- Confirm `git status --short` is empty.
- Run the relevant tests again from `main`.
- Deploy with `scripts/deploy_public_site.sh prod outputs/public-site`.
- Smoke `https://vhf.robertboscacci.com`.
