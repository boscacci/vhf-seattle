from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from talkingboats.spool_uploader import (
    SpooledAudioClip,
    UploadResult,
    discover_completed_audio_files,
    infer_spool_channel,
    process_spool_once,
    upload_spooled_clip,
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


def test_spool_uploader_derives_clip_end_from_probed_audio_duration(tmp_path) -> None:
    channel_dir = tmp_path / "14"
    channel_dir.mkdir()
    audio_path = channel_dir / "vhf-14_20260706_042307.mp3"
    audio_path.write_bytes(b"audio")
    now = datetime(2026, 7, 6, 4, 24, tzinfo=UTC)
    old_timestamp = (now - timedelta(seconds=20)).timestamp()

    clips = discover_completed_audio_files(
        spool_root=tmp_path,
        now=now,
        min_age_seconds=10,
        stat_func=lambda path: FakeStat(size=path.stat().st_size, mtime=old_timestamp),
        duration_probe=lambda path: 3.25,
    )

    assert len(clips) == 1
    assert clips[0].duration_seconds == 3.25
    assert clips[0].ended_at == datetime(2026, 7, 6, 4, 23, 10, 250000, tzinfo=UTC)


def test_spool_uploader_limits_duration_probes_to_newest_candidates(tmp_path) -> None:
    channel_dir = tmp_path / "14"
    channel_dir.mkdir()
    now = datetime(2026, 7, 6, 4, 30, tzinfo=UTC)
    audio_paths = [
        channel_dir / f"vhf-14_20260706_04{minute:02d}00.mp3" for minute in range(20, 30)
    ]
    modified_at = {}
    for index, audio_path in enumerate(audio_paths):
        audio_path.write_bytes(b"audio")
        modified_at[audio_path] = (now - timedelta(minutes=10 - index)).timestamp()
    probed_paths = []

    clips = discover_completed_audio_files(
        spool_root=tmp_path,
        now=now,
        min_age_seconds=10,
        max_candidates=2,
        stat_func=lambda path: FakeStat(size=path.stat().st_size, mtime=modified_at[path]),
        duration_probe=lambda path: probed_paths.append(path) or 1.0,
    )

    assert [clip.audio_path for clip in clips] == audio_paths[-1:-3:-1]
    assert probed_paths == audio_paths[-1:-3:-1]


def test_spool_uploader_ignores_bad_sidecar_end_and_uses_duration(tmp_path) -> None:
    channel_dir = tmp_path / "14"
    channel_dir.mkdir()
    audio_path = channel_dir / "vhf-14_20260706_042307.mp3"
    audio_path.write_bytes(b"audio")
    audio_path.with_suffix(".json").write_text(
        json.dumps(
            {
                "started_at": "2026-07-06T04:23:07Z",
                "ended_at": "2026-07-06T04:23:07Z",
                "duration_seconds": 3.25,
            }
        ),
        encoding="utf-8",
    )
    now = datetime(2026, 7, 6, 4, 24, tzinfo=UTC)
    old_timestamp = (now - timedelta(seconds=20)).timestamp()

    clips = discover_completed_audio_files(
        spool_root=tmp_path,
        now=now,
        min_age_seconds=10,
        stat_func=lambda path: FakeStat(size=path.stat().st_size, mtime=old_timestamp),
        duration_probe=lambda path: None,
    )

    assert len(clips) == 1
    assert clips[0].started_at == datetime(2026, 7, 6, 4, 23, 7, tzinfo=UTC)
    assert clips[0].duration_seconds == 3.25
    assert clips[0].ended_at == datetime(2026, 7, 6, 4, 23, 10, 250000, tzinfo=UTC)


def test_upload_spooled_clip_posts_duration_metadata(monkeypatch, tmp_path) -> None:
    audio_path = tmp_path / "vhf-14_20260706_042307.mp3"
    audio_path.write_bytes(b"audio")
    started_at = datetime(2026, 7, 6, 4, 23, 7, tzinfo=UTC)
    ended_at = started_at + timedelta(seconds=3.25)
    posts = []

    class FakeUrlopenResponse:
        def __init__(self, body: bytes = b"") -> None:
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *_exc_info):
            return False

        def read(self) -> bytes:
            return self.body

    def fake_urlopen(request, timeout):
        if request.method == "POST":
            posts.append(json.loads(request.data.decode("utf-8")))
            return FakeUrlopenResponse(
                json.dumps(
                    {
                        "bucket": "raw-bucket",
                        "key": "raw/channel=14/date=2026-07-06/fake.mp3",
                        "upload_url": "https://s3.example.test/upload",
                        "required_headers": {"Content-Type": "audio/mpeg"},
                    }
                ).encode("utf-8")
            )
        if request.method == "PUT":
            return FakeUrlopenResponse()
        raise AssertionError(f"unexpected request method: {request.method}")

    monkeypatch.setattr("talkingboats.spool_uploader.urllib.request.urlopen", fake_urlopen)

    upload_spooled_clip(
        api_url="http://private-api.test",
        ingest_token="ingest-token",
        clip=SpooledAudioClip(
            channel="14",
            audio_path=audio_path,
            started_at=started_at,
            content_type="audio/mpeg",
            idempotency_key="spool-v1:14:2026-07-06T04:23:07Z:test",
            ended_at=ended_at,
            duration_seconds=3.25,
        ),
    )

    assert posts == [
        {
            "channel": "14",
            "started_at": "2026-07-06T04:23:07Z",
            "ended_at": "2026-07-06T04:23:10.250000Z",
            "duration_seconds": 3.25,
            "content_type": "audio/mpeg",
            "idempotency_key": "spool-v1:14:2026-07-06T04:23:07Z:test",
        }
    ]


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


def test_spool_uploader_does_not_infer_channel_from_unrelated_ancestors(tmp_path) -> None:
    spool_root = tmp_path / "pytest-10" / "spool"
    unknown_dir = spool_root / "unknown"
    known_dir = spool_root / "14"
    unknown_dir.mkdir(parents=True)
    known_dir.mkdir()
    unknown = unknown_dir / "vhf-99_20260605_123221.mp3"
    known = known_dir / "vhf-14_20260605_123222.mp3"
    unknown.write_bytes(b"unknown audio")
    known.write_bytes(b"known audio")
    old_timestamp = datetime(2026, 6, 5, 12, 33, tzinfo=UTC).timestamp()

    clips = discover_completed_audio_files(
        spool_root=spool_root,
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


def test_spool_uploader_discards_old_completed_files_beyond_retention_cap(tmp_path) -> None:
    channel_dir = tmp_path / "14"
    channel_dir.mkdir()
    now = datetime(2026, 5, 28, 1, 0, tzinfo=UTC)
    clips = [
        channel_dir / f"vhf-14_20260528_00{minute:02d}00.mp3" for minute in range(56, 60)
    ]
    old_timestamp = (now - timedelta(seconds=20)).timestamp()
    for clip in clips:
        clip.write_bytes(b"audio")
    uploaded: list[str] = []

    def fake_upload(*, api_url, ingest_token, clip):
        uploaded.append(clip.audio_path.name)
        return UploadResult(
            bucket="bucket",
            key=f"raw/channel={clip.channel}/clip.mp3",
            bytes_uploaded=5,
        )

    count = process_spool_once(
        spool_root=tmp_path,
        api_url="http://private-api.test",
        ingest_token="ingest-token",
        min_age_seconds=10,
        delete_after_upload=False,
        now=now,
        stat_func=lambda path: FakeStat(size=path.stat().st_size, mtime=old_timestamp),
        duration_probe=lambda path: None,
        upload_func=fake_upload,
        max_files=1,
        max_retained_files=2,
    )

    assert count == 1
    assert uploaded == [clips[-1].name]
    assert {path.name for path in channel_dir.glob("*.mp3")} == {
        clips[-2].name,
        clips[-1].name,
    }


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
        fallback_to_original_on_prepare_error=False,
    )

    assert count == 1
    assert uploaded == ["vhf-14_20260528_004700-edge.mp3"]
    assert not bad.exists()
    assert (failed_root / "13" / bad.name).read_bytes() == b"bad mp3"
    assert not good.exists()


def test_spool_uploader_upload_failure_does_not_block_later_files(tmp_path) -> None:
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

    def fake_upload(*, api_url, ingest_token, clip):
        if clip.audio_path == bad:
            raise RuntimeError("presign failed")
        uploaded.append(clip.audio_path.name)
        return UploadResult(
            bucket="bucket",
            key=f"raw/channel={clip.channel}/clip.mp3",
            bytes_uploaded=8,
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
        duration_probe=lambda path: None,
    )

    assert count == 1
    assert uploaded == [good.name]
    assert bad.exists()
    assert not good.exists()


def test_spool_uploader_uploads_original_when_optimization_fails(tmp_path) -> None:
    channel_dir = tmp_path / "16"
    channel_dir.mkdir()
    source = channel_dir / "vhf-16_20260704_194027.mp3"
    source.write_bytes(b"original airband mp3")
    old_timestamp = datetime(2026, 7, 4, 19, 41, tzinfo=UTC).timestamp()
    uploaded = []

    def fake_run(command, *, check):
        raise subprocess.CalledProcessError(returncode=183, cmd=command)

    def fake_upload(*, api_url, ingest_token, clip):
        uploaded.append((clip.audio_path, clip.content_type, clip.audio_path.read_bytes()))
        return UploadResult(
            bucket="bucket",
            key=f"raw/channel={clip.channel}/original.mp3",
            bytes_uploaded=18,
        )

    count = process_spool_once(
        spool_root=tmp_path,
        api_url="http://private-api.test",
        ingest_token="ingest-token",
        min_age_seconds=10,
        delete_after_upload=True,
        now=datetime(2026, 7, 4, 19, 42, tzinfo=UTC),
        stat_func=lambda path: FakeStat(size=path.stat().st_size, mtime=old_timestamp),
        upload_func=fake_upload,
        audio_filter="highpass=f=250,acompressor=threshold=0.06",
        ffmpeg_path="ffmpeg",
        runner=fake_run,
        failed_root=tmp_path / "failed",
    )

    assert count == 1
    assert uploaded == [(source, "audio/mpeg", b"original airband mp3")]
    assert not source.exists()
    assert not (tmp_path / "failed").exists()


def test_spool_uploader_quarantines_stale_empty_completed_files(tmp_path) -> None:
    failed_root = tmp_path / "failed"
    empty_dir = tmp_path / "14"
    good_dir = tmp_path / "74"
    empty_dir.mkdir()
    good_dir.mkdir()
    empty = empty_dir / "vhf-14_20260704_003602.mp3"
    good = good_dir / "vhf-74_20260704_194500.mp3"
    empty.write_bytes(b"")
    good.write_bytes(b"good mp3")
    old_timestamp = datetime(2026, 7, 4, 19, 40, tzinfo=UTC).timestamp()
    uploaded = []

    def fake_upload(*, api_url, ingest_token, clip):
        uploaded.append(clip.audio_path.name)
        return UploadResult(
            bucket="bucket",
            key=f"raw/channel={clip.channel}/clip.mp3",
            bytes_uploaded=8,
        )

    count = process_spool_once(
        spool_root=tmp_path,
        api_url="http://private-api.test",
        ingest_token="ingest-token",
        min_age_seconds=10,
        delete_after_upload=True,
        now=datetime(2026, 7, 4, 19, 41, tzinfo=UTC),
        stat_func=lambda path: FakeStat(size=path.stat().st_size, mtime=old_timestamp),
        upload_func=fake_upload,
        failed_root=failed_root,
    )

    assert count == 1
    assert uploaded == [good.name]
    assert not empty.exists()
    assert not good.exists()
    assert (failed_root / "14" / empty.name).read_bytes() == b""
    sidecar = failed_root / "14" / f"{empty.name}.error.json"
    assert "stale empty spool file" in sidecar.read_text(encoding="utf-8")


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
