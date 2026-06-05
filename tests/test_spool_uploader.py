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


def test_spool_uploader_infers_channel_from_vhf_filename() -> None:
    assert (
        infer_spool_channel(Path("/opt/talkingboats/spool/airband/vhf-67_20260529_004440.mp3"))
        == "67"
    )
    assert (
        infer_spool_channel(Path("/opt/talkingboats/spool/airband/vhf-05A_20260529_004440.mp3"))
        == "05A"
    )
    assert (
        infer_spool_channel(Path("/opt/talkingboats/spool/airband/vhf-65a_20260605_123221.mp3"))
        == "65A"
    )
    assert (
        infer_spool_channel(Path("/opt/talkingboats/spool/airband/78A/vhf-78a_20260605_123221.mp3"))
        == "78A"
    )


def test_spool_uploader_skips_unknown_channel_files_and_keeps_discovering(tmp_path) -> None:
    unknown_dir = tmp_path / "99"
    known_dir = tmp_path / "14"
    unknown_dir.mkdir()
    known_dir.mkdir()
    unknown = unknown_dir / "vhf-99_20260605_123221.mp3"
    known = known_dir / "vhf-14_20260605_123222.mp3"
    unknown.write_bytes(b"unknown audio")
    known.write_bytes(b"known audio")
    old_timestamp = datetime(2026, 6, 5, 12, 33, tzinfo=UTC).timestamp()

    clips = discover_completed_audio_files(
        spool_root=tmp_path,
        now=datetime(2026, 6, 5, 12, 34, tzinfo=UTC),
        min_age_seconds=10,
        stat_func=lambda path: FakeStat(size=path.stat().st_size, mtime=old_timestamp),
    )

    assert [clip.audio_path for clip in clips] == [known]
    assert clips[0].channel == "14"


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
    assert clip.idempotency_key.startswith("spool-v1:14:2026-05-28T00:46:17Z:")
    assert uploaded_bytes == b"edge optimized mp3"
    assert not clip.audio_path.exists()


def test_spool_uploader_prioritizes_recent_files_when_limited(tmp_path) -> None:
    old_dir = tmp_path / "13"
    new_dir = tmp_path / "14"
    old_dir.mkdir()
    new_dir.mkdir()
    old = old_dir / "vhf-13_20260528_004617.mp3"
    new = new_dir / "vhf-14_20260528_004700.mp3"
    old.write_bytes(b"old audio")
    new.write_bytes(b"new audio")
    uploaded = []

    def fake_upload(*, api_url, ingest_token, clip):
        uploaded.append(clip.audio_path.name)
        return UploadResult(
            bucket="bucket",
            key=f"raw/channel={clip.channel}/clip.mp3",
            bytes_uploaded=9,
        )

    count = process_spool_once(
        spool_root=tmp_path,
        api_url="http://private-api.test",
        ingest_token="ingest-token",
        min_age_seconds=10,
        delete_after_upload=False,
        now=datetime(2026, 5, 28, 0, 49, tzinfo=UTC),
        stat_func=lambda path: FakeStat(
            size=path.stat().st_size,
            mtime=datetime(2026, 5, 28, 0, 48, tzinfo=UTC).timestamp(),
        ),
        upload_func=fake_upload,
        max_files=1,
    )

    assert count == 1
    assert uploaded == [new.name]


def test_spool_uploader_quarantines_failed_preparation_and_continues(tmp_path) -> None:
    failed_root = tmp_path / "failed"
    bad_dir = tmp_path / "13"
    good_dir = tmp_path / "14"
    bad_dir.mkdir()
    good_dir.mkdir()
    bad = bad_dir / "vhf-13_20260528_004617.mp3"
    good = good_dir / "vhf-14_20260528_004700.mp3"
    bad.write_bytes(b"bad mp3")
    good.write_bytes(b"good mp3")
    old_timestamp = datetime(2026, 5, 28, 0, 48, tzinfo=UTC).timestamp()
    uploaded = []

    def fake_run(command, *, check):
        if str(bad) in command:
            raise subprocess.CalledProcessError(returncode=1, cmd=command)
        Path(command[-1]).write_bytes(b"edge optimized mp3")

    def fake_upload(*, api_url, ingest_token, clip):
        uploaded.append(clip.audio_path.name)
        return UploadResult(
            bucket="bucket",
            key=f"raw/channel={clip.channel}/optimized.mp3",
            bytes_uploaded=18,
        )

    count = process_spool_once(
        spool_root=tmp_path,
        api_url="http://private-api.test",
        ingest_token="ingest-token",
        min_age_seconds=10,
        delete_after_upload=True,
        now=datetime(2026, 5, 28, 0, 49, tzinfo=UTC),
        stat_func=lambda path: FakeStat(size=path.stat().st_size, mtime=old_timestamp),
        upload_func=fake_upload,
        audio_filter="highpass=f=250,acompressor=threshold=0.06",
        ffmpeg_path="ffmpeg",
        runner=fake_run,
        failed_root=failed_root,
    )

    assert count == 1
    assert uploaded == ["vhf-14_20260528_004700-edge.mp3"]
    assert not bad.exists()
    assert (failed_root / "13" / bad.name).read_bytes() == b"bad mp3"
    assert not good.exists()


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
