import copy
import runpy

import pytest

MODULE = runpy.run_path("scripts/deploy_live_cdn.py")


def plan():
    base = {
        "path_pattern": "/api/live/channels",
        "target_origin_id": "live-radio-proxy",
        "allowed_methods": ["GET", "HEAD", "OPTIONS"],
        "cached_methods": ["GET", "HEAD"],
        "cache_policy_id": MODULE["DISABLED_CACHE"],
        "origin_request_policy_id": "existing-policy",
        "viewer_protocol_policy": "redirect-to-https",
        "compress": True,
    }
    before = {
        "aliases": ["seattleboatradio.com"],
        "origin": [{"origin_id": "live-radio-proxy"}],
        "enabled": True,
        "ordered_cache_behavior": [base],
    }
    after = copy.deepcopy(before)
    after["ordered_cache_behavior"] += [
        {**copy.deepcopy(base), "path_pattern": path, "compress": not path.endswith(".mp3")}
        for path in sorted(MODULE["PATHS"])
    ]
    return {
        "resource_changes": [
            {
                "address": "aws_cloudfront_distribution.site",
                "mode": "managed",
                "change": {"actions": ["update"], "before": before, "after": after},
            }
        ]
    }


def test_live_cdn_plan_only_adds_approved_uncached_read_only_routes():
    assert set(MODULE["validate_plan"](plan())) == MODULE["PATHS"]


@pytest.mark.parametrize("kind", ["resource", "origin", "private_path", "post", "cache", "delete"])
def test_live_cdn_rejects_unrelated_or_unsafe_plan_changes(kind):
    value = plan()
    resource = value["resource_changes"][0]
    after = resource["change"]["after"]
    if kind == "resource":
        resource["address"] = "aws_iam_policy.operator"
    elif kind == "origin":
        after["origin"] = [{"origin_id": "unreviewed"}]
    elif kind == "private_path":
        after["ordered_cache_behavior"][1]["path_pattern"] = "/api/asr-feedback/*"
    elif kind == "post":
        after["ordered_cache_behavior"][1]["allowed_methods"].append("POST")
    elif kind == "cache":
        after["ordered_cache_behavior"][1]["cache_policy_id"] = "cache-audio"
    elif kind == "delete":
        after["ordered_cache_behavior"].pop(0)
    with pytest.raises(ValueError):
        MODULE["validate_plan"](value)


def test_live_cdn_rollback_removes_only_the_introduced_routes():
    value = plan()
    change = value["resource_changes"][0]["change"]
    change["before"], change["after"] = change["after"], change["before"]
    assert MODULE["validate_plan"](value, rollback_paths=MODULE["PATHS"]) == []
    with pytest.raises(ValueError):
        MODULE["validate_plan"](value, rollback_paths={"/api/live/current.mp3"})


def test_live_cdn_accepts_provider_null_defaults_without_changing_routing():
    value = plan()
    change = value["resource_changes"][0]["change"]
    old, new = (
        change["before"]["ordered_cache_behavior"][0],
        change["after"]["ordered_cache_behavior"][0],
    )
    old.update(default_ttl=0, field_level_encryption_id="", grpc_config=[{"enabled": False}])
    new.update(default_ttl=None, field_level_encryption_id=None, grpc_config=None)
    assert set(MODULE["validate_plan"](value)) == MODULE["PATHS"]
    old["field_level_encryption_id"] = "existing-protected-policy"
    with pytest.raises(ValueError):
        MODULE["validate_plan"](value)


def test_cdn_rollback_source_preserves_routes_not_introduced_by_release(tmp_path):
    from pathlib import Path

    source = tmp_path / "source"
    module = source / "infra/opentofu"
    module.mkdir(parents=True)
    (source / "src").mkdir()
    (module / "main.tf").write_text(Path("infra/opentofu/main.tf").read_text())
    restored = MODULE["rollback_source"](source, tmp_path / "work", ["/api/live/current.mp3"])
    text = (restored / "infra/opentofu/main.tf").read_text()
    assert 'path_pattern             = "/api/live/current.mp3"' not in text
    assert 'path_pattern             = "/api/live/*/current.mp3"' in text
    assert 'path_pattern             = "/api/live/channels"' in text
    assert 'path_pattern             = "/api/clips/recent"' in text


def test_cdn_plan_reuses_only_the_validated_existing_ais_hash():
    values = {"TALKINGBOATS_AIS_INGEST_TOKEN_SHA256": "c" * 64}
    state = {
        "values": {
            "root_module": {
                "resources": [
                    {
                        "address": "aws_lambda_function.ais_ingest",
                        "values": {"environment": [{"variables": values}]},
                    }
                ]
            }
        }
    }
    assert MODULE["existing_ais_hash"](state) == "c" * 64
    values["TALKINGBOATS_AIS_INGEST_TOKEN_SHA256"] = "invalid"
    with pytest.raises(ValueError):
        MODULE["existing_ais_hash"](state)
