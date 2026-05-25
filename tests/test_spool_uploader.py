from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from talkingboats.spool_uploader import discover_completed_audio_files, infer_spool_channel


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


def test_spool_uploader_imports_without_pydantic() -> None:
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
        text=True,
    )

    assert result.stdout.strip() == "ok"


class FakeStat:
    def __init__(self, *, size: int, mtime: float) -> None:
        self.st_size = size
        self.st_mtime = mtime
