"""Require one approval for the exact dev-tested artifact; never infer approval from a tag."""

import json
import sys
from datetime import datetime
from pathlib import Path

approval_path, tag, commit, digest, smoke_path = sys.argv[1:]
a = json.loads(Path(approval_path).read_text())
s = json.loads(Path(smoke_path).read_text())
expected = {"release_tag": tag, "commit": commit, "artifact_sha256": digest, "environment": "prod"}
if any(a.get(k) != v for k, v in expected.items()):
    raise ValueError("approval does not select this exact artifact and production environment")
if (
    not a.get("approved_by")
    or a.get("approval_kind") != "human"
    or not a.get("dev_manually_smoke_tested")
):
    raise ValueError("one explicit human approval after manual dev smoke testing is required")
if datetime.fromisoformat(a["approved_at"].replace("Z", "+00:00")).tzinfo is None:
    raise ValueError("approval timestamp requires a timezone")
if (
    s.get("commit") != commit
    or s.get("artifact_sha256") != digest
    or not s.get("dev_playwright_passed")
):
    raise ValueError("artifact has not passed dev Playwright")
