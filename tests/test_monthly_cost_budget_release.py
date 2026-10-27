import copy
import runpy

import pytest

MODULE = runpy.run_path("scripts/scope_monthly_cost_budget.py")
project_tags = MODULE["project_tags"]
validate_plan = MODULE["validate_plan"]
notification_settings = MODULE["notification_settings"]
FILTER = [{"name": "TagKeyValue", "values": ["user:BillingProject$talkingboats"]}]


def test_notification_verification_allows_alarm_recalculation_but_preserves_thresholds():
    before = [{"Threshold": 25, "NotificationState": "ALARM"}]
    after = [{"Threshold": 25, "NotificationState": "OK"}]
    assert notification_settings(before) == notification_settings(after)
    assert notification_settings(before) != notification_settings([{"Threshold": 35}])


def plan(actions=None, address="aws_budgets_budget.monthly_cost"):
    before = {
        "name": "talkingboats-monthly-cost",
        "limit_amount": "35",
        "notification": [{"threshold": 25}, {"threshold": 35}],
        "cost_filter": [],
        "cost_types": [{"include_tax": True}],
    }
    after = {**before, "cost_filter": FILTER}
    return {
        "resource_changes": [
            {
                "address": address,
                "mode": "managed",
                "change": {
                    "actions": actions or ["update"],
                    "before": before,
                    "after": after,
                },
            }
        ]
    }


def test_budget_release_accepts_only_project_filter_change():
    validate_plan(plan())


@pytest.mark.parametrize("field", ["limit_amount", "notification", "cost_types", "name"])
def test_budget_release_rejects_changes_to_limit_alerts_or_cost_definition(field):
    value = plan()
    value["resource_changes"][0]["change"]["after"][field] = "changed"
    with pytest.raises(ValueError, match="more than"):
        validate_plan(value)


@pytest.mark.parametrize("actions", [["delete", "create"], ["create"], ["delete"]])
def test_budget_release_rejects_replacement_creation_and_deletion(actions):
    with pytest.raises(ValueError, match="unrelated"):
        validate_plan(plan(actions=actions))


def test_budget_release_rejects_other_resource_changes():
    with pytest.raises(ValueError, match="unrelated"):
        validate_plan(plan(address="aws_sns_topic_policy.prod_clip_freshness_alerts"))


@pytest.mark.parametrize("filters", [[], [{"name": "Service", "values": ["Amazon DynamoDB"]}]])
def test_budget_release_rejects_missing_or_wrong_project_filter(filters):
    value = plan()
    value["resource_changes"][0]["change"]["after"]["cost_filter"] = filters
    with pytest.raises(ValueError, match="project filter"):
        validate_plan(value)


def test_budget_release_rejects_removing_an_existing_scope():
    value = plan()
    value["resource_changes"][0]["change"]["before"]["cost_filter"] = [
        {"name": "Service", "values": ["Amazon DynamoDB"]}
    ]
    with pytest.raises(ValueError, match="existing scope"):
        validate_plan(value)


def test_budget_release_retry_accepts_an_already_scoped_budget():
    value = plan(actions=["no-op"])
    value["resource_changes"][0]["change"]["before"]["cost_filter"] = copy.deepcopy(FILTER)
    validate_plan(value)


def test_budget_release_rejects_a_missing_budget():
    with pytest.raises(ValueError, match="missing"):
        validate_plan({"resource_changes": []})


def test_project_tags_preserve_existing_tags_and_are_idempotent():
    original = {"Owner": "rob", "Purpose": "dns"}
    tagged = project_tags(original)
    assert tagged == {
        **original,
        "Application": "elliott-bay-vhf",
        "BillingProject": "talkingboats",
    }
    assert original == {"Owner": "rob", "Purpose": "dns"}
    assert project_tags(tagged) == tagged


@pytest.mark.parametrize(
    "tags",
    [
        {"BillingProject": "another-project"},
        {"Application": "another-application"},
    ],
)
def test_project_tags_reject_conflicting_resource_ownership(tags):
    with pytest.raises(ValueError, match="ownership"):
        project_tags(tags)
