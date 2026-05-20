from datetime import UTC, datetime

from talkingboats.schemas import ClipPresignRequest
from talkingboats.storage import is_allowed_audio_key, raw_clip_key


def test_raw_clip_key_is_stable_and_does_not_include_receiver_details() -> None:
    request = ClipPresignRequest(
        channel="68",
        started_at=datetime(2026, 5, 20, 19, 12, tzinfo=UTC),
        content_type="audio/mpeg",
        idempotency_key="receiver-serial-and-local-path-should-be-hashed",
    )

    key = raw_clip_key(request)

    assert key.startswith("raw/channel=68/date=2026-05-20/20260520T191200Z-")
    assert key.endswith(".mp3")
    assert "receiver-serial" not in key
    assert "local-path" not in key


def test_playback_key_validation_allows_only_audio_prefixes() -> None:
    assert is_allowed_audio_key("raw/channel=14/date=2026-05-20/file.mp3")
    assert is_allowed_audio_key("hall-of-fame/channel=68/file.ogg")

    assert not is_allowed_audio_key("../raw/channel=14/file.mp3")
    assert not is_allowed_audio_key("/raw/channel=14/file.mp3")
    assert not is_allowed_audio_key("public/channel=14/file.mp3")
    assert not is_allowed_audio_key("raw//channel=14/file.mp3")
