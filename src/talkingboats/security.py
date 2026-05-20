from __future__ import annotations

import hmac
import re
from collections.abc import Mapping, Sequence

from fastapi import HTTPException, status

FORBIDDEN_PUBLIC_FIELD_NAMES = {
    "aws_account_id",
    "icecast_url",
    "internal_url",
    "private_notes",
    "private_s3_key",
    "raw_s3_key",
    "receiver_id",
    "stream_url",
}

FORBIDDEN_PUBLIC_VALUE_PATTERNS = [
    re.compile(r"s3://", re.IGNORECASE),
    re.compile(r"\braw/channel=", re.IGNORECASE),
    re.compile(r"\bhall-of-fame/", re.IGNORECASE),
    re.compile(r"X-Amz-", re.IGNORECASE),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"\b\d{12}\b"),
    re.compile(r"https?://(?:10\.|127\.0\.0\.1|172\.(?:1[6-9]|2\d|3[01])\.|192\.168\.)"),
]


def require_token(provided: str | None, expected: str | None, token_name: str) -> None:
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{token_name} is not configured",
        )
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")


def assert_public_safe(value: object) -> None:
    unsafe = find_public_safety_issue(value)
    if unsafe:
        raise ValueError(unsafe)


def find_public_safety_issue(value: object, path: str = "$") -> str | None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            if key_text in FORBIDDEN_PUBLIC_FIELD_NAMES:
                return f"forbidden public field at {path}.{key_text}"
            issue = find_public_safety_issue(item, f"{path}.{key_text}")
            if issue:
                return issue
        return None

    if isinstance(value, str):
        for pattern in FORBIDDEN_PUBLIC_VALUE_PATTERNS:
            if pattern.search(value):
                return f"forbidden public value at {path}"
        return None

    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        for index, item in enumerate(value):
            issue = find_public_safety_issue(item, f"{path}[{index}]")
            if issue:
                return issue
    return None
