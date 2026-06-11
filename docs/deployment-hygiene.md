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
| Browser hostname | `vhf-dev.robertboscacci.com` over Tailscale | `vhf.robertboscacci.com` public |
| Static origin | `dev_public_site_bucket` output | `public_site_bucket` output |
| Raw audio | `dev_raw_audio_bucket` output | `raw_audio_bucket` output |
| CloudFront | disabled legacy dev distribution | `cloudfront_distribution_id` output |
| IAM policy | `dev_server_iam_policy_arn` output | `server_iam_policy_arn` output |

Dev and prod buckets, distributions, certificates, and server IAM policies carry
explicit `Environment` tags. Public buckets stay private. Prod is readable only
through CloudFront Origin Access Control; dev is served from the Ubuntu micro-computer
tailnet deployment.

Route53 points `vhf-dev.robertboscacci.com` at the Ubuntu micro-computer Tailscale address,
not at CloudFront. The Ubuntu micro-computer runs the `deploy/optiplex/vhf-dev-proxy`
front-door container on the tailnet `80/443` addresses. It terminates the
DNS-validated `vhf-dev.robertboscacci.com` certificate, redirects HTTP to HTTPS,
and injects `X-TalkingBoats-Tailnet-Dev: 1` before write-capable operator
requests reach the dev live proxy on `172.20.0.1:8095`. Pi-hole may serve its
admin UI on alternate ports, but it must not bind the Ubuntu micro-computer tailnet `80/443`
front door. The public Funnel path uses a separate read-only live proxy without
tailnet dev routes, so spoofed viewer headers cannot reach write routes. Do not
reintroduce browser bearer-token auth for the transcript feedback loop.

## Operator Checklist

Before dev deploy:

- Confirm the target is `dev`.
- Confirm the branch is `dev`, `main`, `codex/*`, or `feature/*`.
- Run the relevant tests for the changed area.
- Smoke `https://vhf-dev.robertboscacci.com` from a tailnet-connected device.

Before prod deploy:

- Merge the tested dev change into `main`.
- Confirm `git status --short` is empty.
- Run the relevant tests again from `main`.
- Deploy with `scripts/deploy_public_site.sh prod outputs/public-site`.
- Smoke `https://vhf.robertboscacci.com`.
