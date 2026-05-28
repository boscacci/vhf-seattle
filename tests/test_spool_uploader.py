from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from talkingboats.spool_uploader import (
    UploadResult,
    discover_completed_audio_files,
    infer_spool_channel,
    process_spool_once,
)


def test_spool_uploader_discovers_stable_channel_files(tmp_path) -> None:
    channel_dir = tmp_path / "13"
    channel_dir.mkdir()
    audio_path = channel_dir / "vhf-13-20260524T210000Z.mp3"
    audio_path.write_bytes(b"audio")
    now = datetime(2026, 5, 24, 21, 1, tzinfo=UTC)
    old_timestamp = (now - timedelta(seconds=20)).timestamp()
    audio_path.touch()
    Path(audio_path).touch()

    clips = discover_completed_audio_files(
        spool_root=tmp_path,
        now=now,
        min_age_seconds=10,
        stat_func=lambda path: FakeStat(size=path.stat().st_size, mtime=old_timestamp),
    )

    assert len(clips) == 1
    assert clips[0].channel == "13"
    assert clips[0].audio_path == audio_path


def test_spool_uploader_ignores_young_files(tmp_path) -> None:
    channel_dir = tmp_path / "14"
    channel_dir.mkdir()
    audio_path = channel_dir / "vhf-14-active.mp3"
    audio_path.write_bytes(b"audio")
    now = datetime(2026, 5, 24, 21, 1, tzinfo=UTC)

    clips = discover_completed_audio_files(
        spool_root=tmp_path,
        now=now,
        min_age_seconds=10,
        stat_func=lambda path: FakeStat(size=path.stat().st_size, mtime=now.timestamp()),
    )

    assert clips == []


def test_spool_uploader_infers_channel_from_directory() -> None:
    assert infer_spool_channel(Path("/opt/talkingboats/spool/airband/13/file.mp3")) == "13"
    assert infer_spool_channel(Path("/opt/talkingboats/spool/airband/14/file.wav")) == "14"


def test_spool_uploader_optimizes_clip_before_upload(tmp_path) -> None:
    channel_dir = tmp_path / "14"
    channel_dir.mkdir()
    source = channel_dir / "vhf-14_20260528_004617.mp3"
    source.write_bytes(b"raw airband mp3")
    old_timestamp = datetime(2026, 5, 28, 0, 47, tzinfo=UTC).timestamp()
    commands = []
    uploaded = []

    def fake_run(command, *, check):
        commands.append((command, check))
        Path(command[-1]).write_bytes(b"edge optimized mp3")

    def fake_upload(*, api_url, ingest_token, clip):
        uploaded.append((api_url, ingest_token, clip, clip.audio_path.read_bytes()))
        return UploadResult(bucket="bucket", key="raw/channel=14/optimized.mp3", bytes_uploaded=18)

    count = process_spool_once(
        spool_root=tmp_path,
        api_url="http://private-api.test",
        ingest_token="ingest-token",
        min_age_seconds=10,
        delete_after_upload=False,
        now=datetime(2026, 5, 28, 0, 48, tzinfo=UTC),
        stat_func=lambda path: FakeStat(size=path.stat().st_size, mtime=old_timestamp),
        upload_func=fake_upload,
        audio_filter="highpass=f=250,acompressor=threshold=0.06",
        ffmpeg_path="ffmpeg",
        runner=fake_run,
    )

    assert count == 1
    assert source.exists()
    assert commands
    command, check = commands[0]
    assert check is True
    assert "-af" in command
    assert command[command.index("-af") + 1] == "highpass=f=250,acompressor=threshold=0.06"
    assert command[command.index("-codec:a") + 1] == "libmp3lame"
    assert len(uploaded) == 1
    _, _, clip, uploaded_bytes = uploaded[0]
    assert clip.audio_path.suffix == ".mp3"
    assert clip.content_type == "audio/mpeg"
    assert clip.idempotency_key.startswith("spool-v1:14:2026-05-28T00:47:00Z:")
    assert uploaded_bytes == b"edge optimized mp3"
    assert not clip.audio_path.exists()


def test_spool_uploader_imports_without_pydantic() -> None:
    pythonpath = str(Path.cwd() / "src")
    if existing_pythonpath := os.environ.get("PYTHONPATH"):
        pythonpath = f"{pythonpath}{os.pathsep}{existing_pythonpath}"
    import_code = (
        "import sys; "
        "sys.modules['pydantic'] = None; "
        "import talkingboats.spool_uploader; "
        "print('ok')"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            import_code,
        ],
        check=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": pythonpath},
        text=True,
    )

    assert result.stdout.strip() == "ok"


class FakeStat:
    def __init__(self, *, size: int, mtime: float) -> None:
        self.st_size = size
        self.st_mtime = mtime
