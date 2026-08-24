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
  - `seattleboatradio.com` as CloudFront aliases
  - `dev.seattleboatradio.com` as tailnet address records
- Separate dev/prod private raw-audio S3 buckets with tag-filtered `raw/`
  lifecycle expiry: unstarred clips expire after 90 days, starred clips are
  retained
- A production clip-freshness Lambda, five-minute EventBridge schedule,
  CloudWatch alarm, and SNS operator-alert topic
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

## Production freshness alerts

The production monitor reads `public_manifest.json` directly from the private
S3 origin every five minutes and publishes `LatestPublicClipAgeSeconds`,
`PublicManifestAgeSeconds`, and `LatestAisMessageAgeSeconds` in the
`ElliottBayVHF` CloudWatch namespace.

The one-hour clip-content alarm remains visible for diagnosis but has actions
disabled because quiet radio traffic is not a service failure. Operator email
comes from two independent health signals:

- `prod-public-manifest-stale` requires a manifest age of at least one hour for
  three consecutive five-minute samples; and
- `prod-ais-stale` requires an AIS age of at least 15 minutes, or missing
  monitor data, for three consecutive samples.

This preserves content-freshness telemetry while paging on publisher or edge
health. The AIS alarm is also the monitor heartbeat: the Lambda emits all three
metrics in one call, so three missing AIS samples detect a failed or disabled
monitor without turning natural radio silence into an alert.

Email endpoints are intentionally not committed or stored in the OpenTofu
configuration. Subscribe an operator address after the topic exists:

```bash
aws sns subscribe \
  --topic-arn "$(tofu output -raw prod_clip_freshness_alert_topic_arn)" \
  --protocol email \
  --notification-endpoint operator@example.com
```

The operator must accept the AWS confirmation email before alarm notifications
can arrive. Confirm delivery with a temporary state transition on an
action-enabled alarm:

```bash
alarm_name="$(tofu output -raw prod_public_manifest_freshness_alarm_name)"
aws cloudwatch set-alarm-state \
  --alarm-name "${alarm_name}" \
  --state-value ALARM \
  --state-reason "Operator notification smoke test"
aws cloudwatch set-alarm-state \
  --alarm-name "${alarm_name}" \
  --state-value OK \
  --state-reason "Operator notification smoke test complete"
```

For a real alarm, compare the public manifest's `generated_at` and newest clip
timestamp with the Lambda's structured `edge_freshness_observed` log. On the
OptiPlex, verify both `talkingboats-uploaded-clip-transcriber.service` and
`talkingboats-optiplex-healthcheck.timer`; the recurring healthcheck gives the
transcriber up to ten minutes to load its ASR model and finish its first poll
before considering progress stale.

## Clip-count aggregate monitoring

`clip_count_aggregates.tf` adds independent dev and prod DynamoDB Streams
consumers for the serving-index count aggregate. The mappings begin at
`LATEST` and filter to the transcribed, featured, and four queue-status index
partitions. The production consumer has alarms for Lambda errors and stream
iterator age; both notify the existing operator topic.

Apply and validate this infrastructure in dev first. Backfill the specific dev
table with `talkingboats-backfill-clip-counts`, confirm the Lambda has no
errors or lag, then enable the API aggregate flag only after count comparison
and browser smoke tests. Do not enable the flag or apply production resources
as part of a local code change; production promotion still requires the normal
CI approval gate. See `docs/durable-event-store.md` for the exact reversible
rollout sequence.

From the repo root, deploy static files with the helper:

```bash
scripts/deploy_public_site.sh dev outputs/public-site
scripts/deploy_public_site.sh prod outputs/public-site
```

The deploy helper enforces branch hygiene:

- dev deploys: `dev`, `main`, `codex/*`, or `feature/*`
- prod deploys: clean `main` worktree only

See `docs/deployment-hygiene.md` for the full branch/resource policy.
