import json
from pathlib import Path

import pytest

from talkingboats.audio_processing import PublicClipAudioRejected
from talkingboats.clip_transcriber import RecentTranscribedClip, UploadedClipStore
from talkingboats.publish import (
    PublicExportError,
    _public_audio_filename,
    export_public_site,
    export_recent_clip_site,
    sanitize_public_manifest,
)
from talkingboats.schemas import ClipPresignRequest
from talkingboats.security import assert_public_safe


def test_public_manifest_exports_only_reviewed_sanitized_fields() -> None:
    private_manifest = {
        "generated_at": "2026-05-20T00:00:00Z",
        "site": {"title": "Talking Boats"},
        "stats": {"channel_counts": {"68": 1}, "internal_url": "http://127.0.0.1:8034"},
        "ais_tracks": [{"track_id": "track-1", "private_s3_key": "raw/secret.mp3"}],
        "clips": [
            {
                "id": "approved",
                "approved_public": True,
                "public_title": "Public moment",
                "channel": "68",
                "started_at": "2026-05-20T19:12:00Z",
                "transcript_public": "Reviewed summary only.",
                "audio_public_filename": "approved.mp3",
                "private_s3_key": "raw/channel=68/date=2026-05-20/secret.mp3",
                "receiver_id": "rtl-serial",
                "ais_context": {"lat": 47.6062123, "lon": -122.3708844, "speed_knots": 3.2},
                "vessel_context": [{"name": "Private vessel", "private_note": "do not export"}],
            },
            {
                "id": "private",
                "approved_public": False,
                "public_title": "Do not export",
                "channel": "14",
                "started_at": "2026-05-20T20:00:00Z",
                "transcript_public": "This unreviewed text must not leak.",
            },
            {
                "id": "legacy-wx",
                "approved_public": True,
                "public_title": "Legacy broadcast",
                "channel": "WX",
                "started_at": "2026-05-20T21:00:00Z",
                "transcript_public": "Legacy broadcast text.",
            },
        ],
    }

    public_manifest = sanitize_public_manifest(private_manifest)
    rendered = json.dumps(public_manifest)

    assert public_manifest["stats"]["clip_count"] == 1
    assert [clip["id"] for clip in public_manifest["clips"]] == ["approved"]
    assert public_manifest["clips"][0]["ais_context"]["lat"] == 47.606
    assert public_manifest["clips"][0]["ais_context"]["lon"] == -122.371
    assert public_manifest["clips"][0]["vessel_context"] == [{"name": "Private vessel"}]
    assert "ais_tracks" not in public_manifest
    assert "private_s3_key" not in rendered
    assert "receiver_id" not in rendered
    assert "private_note" not in rendered
    assert "127.0.0.1" not in rendered
    assert "unreviewed text" not in rendered


def test_public_manifest_rejects_presigned_urls() -> None:
    with pytest.raises(ValueError, match="forbidden public value"):
        sanitize_public_manifest(
            {
                "clips": [
                    {
                        "id": "bad",
                        "approved_public": True,
                        "public_title": "Bad",
                        "channel": "68",
                        "started_at": "2026-05-20T19:12:00Z",
                        "transcript_public": "https://example.com/audio.mp3?X-Amz-Signature=secret",
                    }
                ]
            }
        )


def test_public_export_copies_static_site_and_writes_manifest(tmp_path: Path) -> None:
    site_source = tmp_path / "site-source"
    site_source.mkdir()
    (site_source / "index.html").write_text("<html></html>", encoding="utf-8")

    private_manifest = tmp_path / "private.json"
    private_manifest.write_text(
        json.dumps(
            {
                "clips": [
                    {
                        "id": "approved",
                        "approved_public": True,
                        "public_title": "Public moment",
                        "channel": "68",
                        "started_at": "2026-05-20T19:12:00Z",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    output_dir = tmp_path / "output"
    export_public_site(private_manifest, site_source, output_dir)

    assert (output_dir / "index.html").exists()
    exported = json.loads((output_dir / "public_manifest.json").read_text(encoding="utf-8"))
    assert exported["clips"][0]["id"] == "approved"


def test_public_export_processes_approved_local_audio(tmp_path: Path) -> None:
    site_source = tmp_path / "site-source"
    site_source.mkdir()
    (site_source / "index.html").write_text("<html></html>", encoding="utf-8")
    audio_source = tmp_path / "audio-source"
    audio_source.mkdir()
    (audio_source / "approved.mp3").write_bytes(b"quiet raw audio")
    private_manifest = tmp_path / "private.json"
    private_manifest.write_text(
        json.dumps(
            {
                "clips": [
                    {
                        "id": "approved",
                        "approved_public": True,
                        "public_title": "Public moment",
                        "channel": "68",
                        "started_at": "2026-05-20T19:12:00Z",
                        "audio_public_filename": "approved.mp3",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    processor = RecordingAudioProcessor()

    export_public_site(
        private_manifest,
        site_source,
        tmp_path / "output",
        audio_source,
        clip_audio_processor=processor,
    )

    assert processor.calls == [
        (audio_source / "approved.mp3", tmp_path / "output" / "clips" / "approved.mp3")
    ]
    assert (tmp_path / "output" / "clips" / "approved.mp3").read_bytes() == (
        b"processed quiet raw audio"
    )


def test_public_export_rejects_nested_audio_filename() -> None:
    with pytest.raises(PublicExportError, match="plain filename"):
        sanitize_public_manifest(
            {
                "clips": [
                    {
                        "id": "bad-audio",
                        "approved_public": True,
                        "public_title": "Bad audio",
                        "channel": "68",
                        "started_at": "2026-05-20T19:12:00Z",
                        "audio_public_filename": "../secret.mp3",
                    }
                ]
            }
        )


def test_public_export_rejects_audio_symlink_escape(tmp_path: Path) -> None:
    site_source = tmp_path / "site-source"
    site_source.mkdir()
    (site_source / "index.html").write_text("<html></html>", encoding="utf-8")
    audio_source = tmp_path / "audio-source"
    audio_source.mkdir()
    outside_audio = tmp_path / "outside.mp3"
    outside_audio.write_bytes(b"private audio")
    (audio_source / "approved.mp3").symlink_to(outside_audio)
    private_manifest = tmp_path / "private.json"
    private_manifest.write_text(
        json.dumps(
            {
                "clips": [
                    {
                        "id": "approved",
                        "approved_public": True,
                        "public_title": "Public moment",
                        "channel": "68",
                        "started_at": "2026-05-20T19:12:00Z",
                        "audio_public_filename": "approved.mp3",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(PublicExportError, match="approved audio file escapes source directory"):
        export_public_site(private_manifest, site_source, tmp_path / "output", audio_source)


def test_recent_clip_export_writes_real_clip_manifest_and_audio(tmp_path: Path) -> None:
    site_source = tmp_path / "site-source"
    site_source.mkdir()
    (site_source / "index.html").write_text("<html></html>", encoding="utf-8")
    db_path = tmp_path / "clips.sqlite3"
    store = UploadedClipStore(db_path)
    request = ClipPresignRequest(
        channel="14",
        started_at="2026-05-24T22:08:41Z",
        ended_at="2026-05-24T22:08:49Z",
        duration_seconds=8.1,
        content_type="audio/mpeg",
        idempotency_key="real-clip",
    )
    key = "raw/channel=14/date=2026-05-24/real.mp3"
    store.record_presigned_upload(key=key, request=request)
    store.mark_transcribed(
        key,
        [
            _segment(
                text="Southwest wind increasing after midnight.",
                started_at="2026-05-24T22:08:41Z",
                ended_at="2026-05-24T22:08:49Z",
            )
        ],
    )
    reader = FakeClipReader({"raw/channel=14/date=2026-05-24/real.mp3": b"real audio"})
    processor = RecordingAudioProcessor()

    manifest = export_recent_clip_site(
        clip_db_path=db_path,
        site_source_dir=site_source,
        output_dir=tmp_path / "output",
        clip_reader=reader,
        clip_audio_processor=processor,
        clip_audio_quality_gate=None,
        limit=10,
    )

    clip = manifest["clips"][0]
    assert clip["channel"] == "14"
    assert clip["channel_label"] == "VTS / Seattle Traffic"
    assert clip["transcript_public"] == "Southwest wind increasing after midnight."
    assert clip["public_title"] == "VHF 14 - May 24, 2026 3:08 PM PDT"
    assert clip["audio_public_filename"].endswith(".mp3")
    assert manifest["stats"]["channel_labels"] == {
        "13": "Bridge-to-bridge",
        "14": "VTS / Seattle Traffic",
        "68": "Recreational",
    }
    exported_audio = tmp_path / "output" / "clips" / clip["audio_public_filename"]
    assert processor.calls == [(processor.calls[0][0], exported_audio)]
    assert processor.source_bytes == [b"real audio"]
    assert exported_audio.read_bytes() == b"processed real audio"
    assert json.loads((tmp_path / "output" / "public_manifest.json").read_text()) == manifest


def test_recent_clip_export_skips_unpublishable_audio_after_download(tmp_path: Path) -> None:
    site_source = tmp_path / "site-source"
    site_source.mkdir()
    (site_source / "index.html").write_text("<html></html>", encoding="utf-8")
    db_path = tmp_path / "clips.sqlite3"
    store = UploadedClipStore(db_path)
    bad_key = "raw/channel=13/date=2026-05-27/bad.mp3"
    good_key = "raw/channel=14/date=2026-05-27/good.mp3"
    store.record_presigned_upload(
        key=bad_key,
        request=ClipPresignRequest(
            channel="13",
            started_at="2026-05-27T19:10:04Z",
            content_type="audio/mpeg",
            idempotency_key="bad-clip",
        ),
    )
    store.mark_transcribed(
        bad_key,
        [
            _segment(
                text="For more information visit www.fema.org",
                started_at="2026-05-27T19:10:04Z",
                ended_at="2026-05-27T19:10:04Z",
            )
        ],
    )
    store.record_presigned_upload(
        key=good_key,
        request=ClipPresignRequest(
            channel="14",
            started_at="2026-05-27T19:09:04Z",
            ended_at="2026-05-27T19:09:09Z",
            duration_seconds=5.0,
            content_type="audio/mpeg",
            idempotency_key="good-clip",
        ),
    )
    store.mark_transcribed(
        good_key,
        [
            _segment(
                text="Seattle Traffic roger.",
                started_at="2026-05-27T19:09:04Z",
                ended_at="2026-05-27T19:09:09Z",
            )
        ],
    )
    reader = FakeClipReader({bad_key: b"silent blip", good_key: b"real traffic"})
    processor = RecordingAudioProcessor()

    def quality_gate(source_path: Path) -> None:
        if source_path.read_bytes() == b"silent blip":
            raise PublicClipAudioRejected("duration 0.216s is below 1.000s")

    manifest = export_recent_clip_site(
        clip_db_path=db_path,
        site_source_dir=site_source,
        output_dir=tmp_path / "output",
        clip_reader=reader,
        clip_audio_processor=processor,
        clip_audio_quality_gate=quality_gate,
        limit=10,
    )

    assert [clip["transcript_public"] for clip in manifest["clips"]] == [
        "Seattle Traffic roger."
    ]
    assert processor.source_bytes == [b"real traffic"]
    assert not any(
        path.name.startswith("20260527T191004Z")
        for path in (tmp_path / "output" / "clips").iterdir()
    )
    assert json.loads((tmp_path / "output" / "public_manifest.json").read_text()) == manifest


def test_recent_clip_public_audio_filename_cannot_look_like_account_id(monkeypatch) -> None:
    class FakeHash:
        def hexdigest(self) -> str:
            return "123456789012abcdef"

    monkeypatch.setattr("talkingboats.publish.hashlib.sha256", lambda _value: FakeHash())
    clip = RecentTranscribedClip(
        key="raw/channel=14/date=2026-05-25/example.mp3",
        channel="14",
        started_at="2026-05-25T00:47:12Z",
        ended_at="2026-05-25T00:47:42Z",
        duration_seconds=30.0,
        content_type="audio/mpeg",
        transcript="forecast text",
        segments=[],
    )

    filename = _public_audio_filename(clip)

    assert filename == "20260525T004712Z-vhf-14-sha123456789012.mp3"
    assert_public_safe({"audio_public_filename": filename})


def test_recent_clip_export_preserves_existing_analysis_artifacts(tmp_path: Path) -> None:
    site_source = tmp_path / "site-source"
    site_source.mkdir()
    (site_source / "index.html").write_text("<html></html>", encoding="utf-8")
    db_path = tmp_path / "clips.sqlite3"
    store = UploadedClipStore(db_path)
    request = ClipPresignRequest(
        channel="14",
        started_at="2026-05-24T22:08:41Z",
        ended_at="2026-05-24T22:08:49Z",
        duration_seconds=8.1,
        content_type="audio/mpeg",
        idempotency_key="real-clip",
    )
    key = "raw/channel=14/date=2026-05-24/real.mp3"
    store.record_presigned_upload(key=key, request=request)
    store.mark_transcribed(
        key,
        [
            _segment(
                text="Seattle Traffic roger.",
                started_at="2026-05-24T22:08:41Z",
                ended_at="2026-05-24T22:08:49Z",
            )
        ],
    )
    output_dir = tmp_path / "output"
    analysis_dir = output_dir / "analysis"
    analysis_dir.mkdir(parents=True)
    (analysis_dir / "lexical.json").write_text('{"status":"ok"}\n', encoding="utf-8")
    (analysis_dir / "topic_clusters.html").write_text("<html>topics</html>\n", encoding="utf-8")

    export_recent_clip_site(
        clip_db_path=db_path,
        site_source_dir=site_source,
        output_dir=output_dir,
        clip_reader=FakeClipReader({key: b"real audio"}),
        clip_audio_processor=RecordingAudioProcessor(),
        clip_audio_quality_gate=None,
        limit=10,
    )

    assert (output_dir / "analysis" / "lexical.json").read_text(encoding="utf-8") == (
        '{"status":"ok"}\n'
    )
    assert "topics" in (output_dir / "analysis" / "topic_clusters.html").read_text(
        encoding="utf-8"
    )


def test_recent_clip_export_reuses_existing_public_audio(tmp_path: Path) -> None:
    site_source = tmp_path / "site-source"
    site_source.mkdir()
    (site_source / "index.html").write_text("<html></html>", encoding="utf-8")
    db_path = tmp_path / "clips.sqlite3"
    store = UploadedClipStore(db_path)
    request = ClipPresignRequest(
        channel="14",
        started_at="2026-05-24T22:08:41Z",
        ended_at="2026-05-24T22:08:49Z",
        duration_seconds=8.1,
        content_type="audio/mpeg",
        idempotency_key="real-clip",
    )
    key = "raw/channel=14/date=2026-05-24/real.mp3"
    store.record_presigned_upload(key=key, request=request)
    store.mark_transcribed(
        key,
        [
            _segment(
                text="Seattle Traffic roger.",
                started_at="2026-05-24T22:08:41Z",
                ended_at="2026-05-24T22:08:49Z",
            )
        ],
    )
    clip = RecentTranscribedClip(
        key=key,
        channel="14",
        started_at="2026-05-24T22:08:41Z",
        ended_at="2026-05-24T22:08:49Z",
        duration_seconds=8.1,
        content_type="audio/mpeg",
        transcript="Seattle Traffic roger.",
        segments=[],
    )
    output_dir = tmp_path / "output"
    clips_dir = output_dir / "clips"
    clips_dir.mkdir(parents=True)
    existing_filename = _public_audio_filename(clip)
    (clips_dir / existing_filename).write_bytes(b"already processed")
    (clips_dir / "stale.mp3").write_bytes(b"stale")
    reader = FakeClipReader({key: b"should not be downloaded"})
    processor = RecordingAudioProcessor()

    manifest = export_recent_clip_site(
        clip_db_path=db_path,
        site_source_dir=site_source,
        output_dir=output_dir,
        clip_reader=reader,
        clip_audio_processor=processor,
        clip_audio_quality_gate=None,
        limit=10,
    )

    assert manifest["clips"][0]["audio_public_filename"] == existing_filename
    assert (output_dir / "clips" / existing_filename).read_bytes() == b"already processed"
    assert not (output_dir / "clips" / "stale.mp3").exists()
    assert reader.downloads == []
    assert processor.calls == []


class FakeClipReader:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects
        self.downloads: list[str] = []

    def download(self, key: str, output_path: Path) -> None:
        self.downloads.append(key)
        output_path.write_bytes(self.objects[key])


class RecordingAudioProcessor:
    def __init__(self) -> None:
        self.calls: list[tuple[Path, Path]] = []
        self.source_bytes: list[bytes] = []

    def __call__(self, source_path: Path, output_path: Path) -> None:
        self.calls.append((source_path, output_path))
        source_bytes = source_path.read_bytes()
        self.source_bytes.append(source_bytes)
        output_path.write_bytes(b"processed " + source_bytes)


def _segment(*, text: str, started_at: str, ended_at: str) -> object:
    from types import SimpleNamespace

    return SimpleNamespace(
        text=text,
        started_at=started_at,
        ended_at=ended_at,
        relative_start_seconds=0.0,
        relative_end_seconds=8.0,
    )
