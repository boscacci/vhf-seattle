"""Plan or apply only the approved public live routes through the shared OpenTofu state."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import boto3

PATHS = {
    "/api/live/current.mp3",
    "/api/live/*/current.mp3",
    "/api/live/status",
    "/api/live/*/status",
}
DISABLED_CACHE = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
STABLE = (
    "aliases",
    "origin",
    "default_cache_behavior",
    "enabled",
    "viewer_certificate",
    "web_acl_id",
    "restrictions",
    "custom_error_response",
    "logging_config",
    "http_version",
    "is_ipv6_enabled",
    "price_class",
    "default_root_object",
    "tags",
)


def normalized_behavior(rule):
    result = {}
    for key, value in rule.items():
        if key in {"min_ttl", "default_ttl", "max_ttl"} and rule.get("cache_policy_id"):
            continue  # Attached cache policy defines these values, not legacy TTL fields.
        if value is None or value == "" or value is False or value == []:
            continue
        if key == "grpc_config" and value == [{"enabled": False}]:
            continue
        result[key] = value
    return result


def validate_plan(plan, *, rollback_paths=None):
    introduced = []
    for resource in plan.get("resource_changes", []):
        change = resource["change"]
        actions = change["actions"]
        if actions == ["no-op"] or (resource.get("mode") == "data" and actions == ["read"]):
            continue
        if resource["address"] != "aws_cloudfront_distribution.site" or actions != ["update"]:
            raise ValueError("CDN plan changes an unrelated resource")
        before, after = change["before"], change["after"]
        if any(before.get(key) != after.get(key) for key in STABLE):
            raise ValueError("CDN plan changes more than live routing")
        old = {r["path_pattern"]: r for r in before["ordered_cache_behavior"]}
        new = {r["path_pattern"]: r for r in after["ordered_cache_behavior"]}
        added, removed = set(new) - set(old), set(old) - set(new)
        if rollback_paths is None:
            if removed or not added <= PATHS:
                raise ValueError("CDN plan removes routes or exposes an unapproved path")
        elif added or not removed <= set(rollback_paths) <= PATHS:
            raise ValueError("CDN rollback exceeds the introduced routes")
        if any(
            normalized_behavior(old[path]) != normalized_behavior(new[path])
            for path in set(old) & set(new)
        ):
            raise ValueError("CDN plan changes an existing route")
        if [p for p in new if p in old] != [p for p in old if p in new]:
            raise ValueError("CDN plan changes existing route precedence")
        for path in added:
            rule = new[path]
            if (
                rule["target_origin_id"] != "live-radio-proxy"
                or set(rule["allowed_methods"]) != {"GET", "HEAD", "OPTIONS"}
                or set(rule["cached_methods"]) != {"GET", "HEAD"}
                or rule["cache_policy_id"] != DISABLED_CACHE
                or rule["origin_request_policy_id"]
                != old["/api/live/channels"]["origin_request_policy_id"]
                or rule["viewer_protocol_policy"] != "redirect-to-https"
                or (path.endswith(".mp3") and rule["compress"])
            ):
                raise ValueError("CDN live route violates the reviewed read-only policy")
        introduced.extend(sorted(added))
    return introduced


def rollback_source(source, work, paths):
    if not set(paths) <= PATHS:
        raise ValueError("invalid rollback routes")
    root = work / "rollback-source"
    module = root / "infra/opentofu"
    shutil.copytree(
        source / "infra/opentofu",
        module,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(".terraform", "terraform.tfstate*", "*.tfplan"),
    )
    src = root / "src"
    if not src.exists():
        src.symlink_to(source / "src", target_is_directory=True)
    if src.resolve() != (source / "src").resolve():
        raise ValueError("rollback source identity mismatch")
    config = module / "main.tf"

    def keep(match):
        path = re.search(r'path_pattern\s*=\s*"([^"]+)"', match[0])
        return "" if path and path[1] in paths else match[0]

    config.write_text(
        re.sub(r"\n  ordered_cache_behavior \{[^{}]*\n  \}", keep, config.read_text())
    )
    return root


def operation_root(source):
    values = dict(
        line.partition("=")[::2]
        for line in (Path.home() / ".config/talkingboats/asr.env").read_text().splitlines()
    )
    storage = Path(values["TALKINGBOATS_ASR_OUTPUT_DIR"]).parent.resolve()
    if str(storage).startswith("/mnt/") and not Path("/mnt/" + storage.parts[2]).is_mount():
        raise ValueError("data volume is not mounted")
    marker = source / "release-commit"
    identity = marker.read_text().strip() if marker.exists() else "proposed-cdn"
    path = storage / "release-operations" / identity / "live-cdn"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def existing_ais_hash(state):
    for resource in state.get("values", {}).get("root_module", {}).get("resources", []):
        if resource["address"] == "aws_lambda_function.ais_ingest":
            value = resource["values"]["environment"][0]["variables"].get(
                "TALKINGBOATS_AIS_INGEST_TOKEN_SHA256", ""
            )
            if re.fullmatch(r"[0-9a-f]{64}", value):
                return value
    raise ValueError("existing AIS authentication hash is unavailable")


def execute(action, source):
    os.umask(0o077)
    work = operation_root(source)
    record = work / "introduced-paths.json"
    if action != "plan" and not (source / "release-commit").exists():
        raise ValueError("cloud changes require the versioned release artifact")
    paths = None
    if action == "rollback":
        if not record.exists():
            return
        paths = json.loads(record.read_text())
        if not paths:
            return
        source = rollback_source(source, work, paths)
    module = source / "infra/opentofu"
    expected = re.search(
        r"talkingboats-opentofu-state-([0-9]{12})", (module / "versions.tf").read_text()
    )
    if not expected or boto3.client("sts").get_caller_identity()["Account"] != expected[1]:
        raise ValueError("AWS account does not own this release's state")
    cache = work.parents[2] / "opentofu-provider-cache"
    cache.mkdir(mode=0o700, exist_ok=True)
    env = dict(
        os.environ,
        TF_DATA_DIR=str(work / ("data-rollback" if action == "rollback" else "data")),
        TF_PLUGIN_CACHE_DIR=str(cache),
        GOMAXPROCS="2",
    )
    tofu = os.environ.get("TALKINGBOATS_TOFU_BIN", str(Path.home() / ".local/bin/tofu"))
    prefix = [tofu, f"-chdir={module}"]
    plan_path = work / f"{action}.tfplan"
    log = work / f"{action}.log"
    with log.open("w") as stream:
        subprocess.run(
            prefix + ["init", "-input=false", "-lockfile=readonly", "-no-color"],
            env=env,
            stdout=stream,
            stderr=stream,
            check=True,
            timeout=180,
        )
        state = json.loads(subprocess.check_output(prefix + ["show", "-json"], env=env))
        env["TF_VAR_ais_ingest_token_sha256"] = existing_ais_hash(state)
        subprocess.run(
            prefix
            + [
                "plan",
                "-input=false",
                "-no-color",
                "-lock-timeout=60s",
                "-target=aws_cloudfront_distribution.site",
                f"-out={plan_path}",
            ],
            env=env,
            stdout=stream,
            stderr=stream,
            check=True,
            timeout=180,
        )
        result = subprocess.check_output(prefix + ["show", "-json", str(plan_path)], env=env)
        (work / f"{action}-plan.json").write_bytes(result)
        introduced = validate_plan(json.loads(result), rollback_paths=paths)
        print(
            json.dumps(
                {
                    "event": "live_cdn_plan_validated",
                    "action": action,
                    "introduced_routes": introduced,
                }
            ),
            flush=True,
        )
        if action == "plan":
            return
        if action == "apply" and not record.exists():
            record.write_text(json.dumps(introduced) + "\n")
        subprocess.run(
            prefix + ["apply", "-input=false", "-no-color", str(plan_path)],
            env=env,
            stdout=stream,
            stderr=stream,
            check=True,
            timeout=600,
        )
    print(json.dumps({"event": "live_cdn_operation_complete", "action": action}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["plan", "apply", "rollback"])
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    try:
        execute(args.action, args.source.resolve())
    except Exception as exc:
        if args.action == "apply":
            try:
                execute("rollback", args.source.resolve())
            except Exception:
                print('{"event":"live_cdn_rollback_failed","private_logs_retained":true}')
        print(
            json.dumps(
                {
                    "event": "live_cdn_operation_failed",
                    "action": args.action,
                    "error_type": type(exc).__name__,
                    "reason": str(exc)
                    if isinstance(exc, ValueError)
                    else "Inspect private OpenTofu logs",
                    "private_logs_retained": True,
                }
            ),
            flush=True,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
