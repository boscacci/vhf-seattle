"""Plan/apply the project budget filter and missing DNS/state-bucket billing tags."""

from __future__ import annotations

import argparse
import json
import os
import runpy
import subprocess
import tempfile
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[1]
ACCOUNT = "062008221187"
BUDGET = "talkingboats-monthly-cost"
BUCKET = f"talkingboats-opentofu-state-{ACCOUNT}"
DOMAIN = "seattleboatradio.com."
TAGS = {"Application": "elliott-bay-vhf", "BillingProject": "talkingboats"}
FILTER = [{"name": "TagKeyValue", "values": ["user:BillingProject$talkingboats"]}]


def project_tags(existing):
    if any(key in existing and existing[key] != value for key, value in TAGS.items()):
        raise ValueError("Resource tags indicate conflicting project ownership")
    return {**existing, **TAGS}


def validate_plan(plan):
    found = False
    for resource in plan.get("resource_changes", []):
        change = resource["change"]
        actions = change["actions"]
        if resource.get("mode") == "data" and actions in (["read"], ["no-op"]):
            continue
        if resource["address"] != "aws_budgets_budget.monthly_cost":
            if actions == ["no-op"]:
                continue
            raise ValueError("Budget plan changes an unrelated resource")
        found = True
        if actions not in (["update"], ["no-op"]):
            raise ValueError("Budget plan replaces or changes an unrelated resource")
        before, after = change["before"], change["after"]
        if after.get("cost_filter") != FILTER:
            raise ValueError("Budget plan does not enforce the exact project filter")
        if before.get("cost_filter") not in (None, [], FILTER):
            raise ValueError("Budget plan replaces a different existing scope")
        if any(
            before.get(k) != after.get(k)
            for k in before.keys() | after.keys()
            if k != "cost_filter"
        ):
            raise ValueError("Budget plan changes more than the project filter")
    if not found:
        raise ValueError("Budget is missing from the plan")


def emit(event, **details):
    print(json.dumps({"event": event, **details}), flush=True)


def notification_settings(rows):
    # AWS recalculates alarm state when the budget scope changes.
    return sorted(
        json.dumps({k: v for k, v in row.items() if k != "NotificationState"}, sort_keys=True)
        for row in rows
    )


def execute(apply):
    session = boto3.Session()
    config = Config(
        connect_timeout=10, read_timeout=30, retries={"mode": "standard", "max_attempts": 3}
    )

    def client(service, region="us-east-1"):
        return session.client(service, region_name=region, config=config)

    if client("sts").get_caller_identity()["Account"] != ACCOUNT:
        raise ValueError("AWS account does not own this project's infrastructure")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("Budget release requires a clean version-controlled checkout")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    allocation = client("ce").list_cost_allocation_tags(TagKeys=["BillingProject"])
    if not any(t["Status"] == "Active" for t in allocation["CostAllocationTags"]):
        raise ValueError("BillingProject must be an active cost-allocation tag")

    dns = client("route53")
    zones = [
        z
        for z in dns.list_hosted_zones_by_name(DNSName=DOMAIN)["HostedZones"]
        if z["Name"] == DOMAIN and not z["Config"]["PrivateZone"]
    ]
    if len(zones) != 1:
        raise ValueError("Project public DNS zone is missing or ambiguous")
    zone_id = zones[0]["Id"].split("/")[-1]
    dns_tags = {
        t["Key"]: t["Value"]
        for t in dns.list_tags_for_resource(ResourceType="hostedzone", ResourceId=zone_id)[
            "ResourceTagSet"
        ]["Tags"]
    }
    desired_dns = project_tags(dns_tags)
    s3 = client("s3", "us-west-2")
    s3.head_bucket(Bucket=BUCKET, ExpectedBucketOwner=ACCOUNT)
    try:
        existing = s3.get_bucket_tagging(Bucket=BUCKET, ExpectedBucketOwner=ACCOUNT)["TagSet"]
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "NoSuchTagSet":
            raise
        existing = []
    bucket_tags = {t["Key"]: t["Value"] for t in existing}
    desired_bucket = project_tags(bucket_tags)
    budget_api = client("budgets")
    notifications = budget_api.describe_notifications_for_budget(
        AccountId=ACCOUNT, BudgetName=BUDGET
    )["Notifications"]

    prefix = ["tofu", f"-chdir={ROOT / 'infra/opentofu'}"]
    helpers = runpy.run_path(str(ROOT / "scripts/deploy_live_cdn.py"))
    env = {**os.environ, "GOMAXPROCS": "2"}
    with tempfile.TemporaryDirectory(prefix="talkingboats-budget-") as scratch:
        plan_file = Path(scratch) / "budget.tfplan"
        with (Path(scratch) / "tofu.log").open("w+") as log:

            def run(args):
                subprocess.run(
                    prefix + args, env=env, stdout=log, stderr=log, check=True, timeout=180
                )

            run(["init", "-input=false", "-lockfile=readonly", "-no-color"])
            state = json.loads(subprocess.check_output(prefix + ["show", "-json"], env=env))
            env["TF_VAR_ais_ingest_token_sha256"] = helpers["existing_ais_hash"](state)
            del state
            run(
                [
                    "plan",
                    "-input=false",
                    "-no-color",
                    "-lock-timeout=30s",
                    "-target=aws_budgets_budget.monthly_cost",
                    f"-out={plan_file}",
                ]
            )
            plan = json.loads(
                subprocess.check_output(prefix + ["show", "-json", str(plan_file)], env=env)
            )
            validate_plan(plan)
            emit(
                "budget_scope_plan_validated",
                commit=commit,
                budget=BUDGET,
                filter=FILTER,
                dns_tags_needed=dns_tags != desired_dns,
                state_bucket_tags_needed=bucket_tags != desired_bucket,
            )
            if not apply:
                return
            if dns_tags != desired_dns:
                dns.change_tags_for_resource(
                    ResourceType="hostedzone",
                    ResourceId=zone_id,
                    AddTags=[{"Key": k, "Value": v} for k, v in TAGS.items()],
                )
            if bucket_tags != desired_bucket:
                s3.put_bucket_tagging(
                    Bucket=BUCKET,
                    ExpectedBucketOwner=ACCOUNT,
                    Tagging={"TagSet": [{"Key": k, "Value": v} for k, v in desired_bucket.items()]},
                )
            emit("project_billing_tags_reconciled", dns_zone=DOMAIN, state_bucket=BUCKET)
            run(["apply", "-input=false", "-no-color", str(plan_file)])

    budget = budget_api.describe_budget(AccountId=ACCOUNT, BudgetName=BUDGET)["Budget"]
    if budget.get("CostFilters") != {"TagKeyValue": FILTER[0]["values"]}:
        raise ValueError("Live budget does not match the project filter")
    current_notifications = budget_api.describe_notifications_for_budget(
        AccountId=ACCOUNT, BudgetName=BUDGET
    )["Notifications"]

    if notification_settings(notifications) != notification_settings(current_notifications):
        raise ValueError("Budget notifications changed during release")
    live_dns = {
        t["Key"]: t["Value"]
        for t in dns.list_tags_for_resource(ResourceType="hostedzone", ResourceId=zone_id)[
            "ResourceTagSet"
        ]["Tags"]
    }
    live_bucket = {
        t["Key"]: t["Value"]
        for t in s3.get_bucket_tagging(Bucket=BUCKET, ExpectedBucketOwner=ACCOUNT)["TagSet"]
    }
    if live_dns != desired_dns or live_bucket != desired_bucket:
        raise ValueError("Project billing tags did not persist")
    emit(
        "budget_scope_verified",
        commit=commit,
        budget=BUDGET,
        filter=budget["CostFilters"],
        limit=budget["BudgetLimit"],
        notifications_preserved=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Apply the validated scoped plan")
    args = parser.parse_args()
    try:
        execute(args.apply)
    except Exception as exc:
        emit(
            "budget_scope_failed",
            error_type=type(exc).__name__,
            reason=str(exc) if isinstance(exc, ValueError) else "AWS or OpenTofu operation failed",
        )
        raise SystemExit(1) from None
