import json
from pathlib import Path

import pytest

from talkingboats.publish import PublicExportError, export_public_site, sanitize_public_manifest


def test_public_manifest_exports_only_reviewed_sanitized_fields() -> None:
    private_manifest = {
        "generated_at": "2026-05-20T00:00:00Z",
        "site": {"title": "Talking Boats"},
        "stats": {"channel_counts": {"68": 1}, "internal_url": "http://127.0.0.1:8034"},
        "ais_tracks": [
            {
                "track_id": "track-1",
                "name": "Mock vessel",
                "vessel_type": "recreational",
                "private_s3_key": "raw/channel=68/date=2026-05-20/secret.mp3",
                "points": [
                    {
                        "observed_at": "2026-05-20T19:10:00Z",
                        "lat": 47.6062123,
                        "lon": -122.3708844,
                        "speed_knots": 4.2,
                        "course_degrees": 212.2,
                        "receiver_id": "rtl-secret",
                    }
                ],
            }
        ],
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
            },
            {
                "id": "private",
                "approved_public": False,
                "public_title": "Do not export",
                "channel": "14",
                "started_at": "2026-05-20T20:00:00Z",
                "transcript_public": "This unreviewed text must not leak.",
            },
        ],
    }

    public_manifest = sanitize_public_manifest(private_manifest)
    rendered = json.dumps(public_manifest)

    assert public_manifest["stats"]["clip_count"] == 1
    assert public_manifest["ais_tracks"][0]["points"][0]["lat"] == 47.606
    assert public_manifest["ais_tracks"][0]["points"][0]["lon"] == -122.371
    assert [clip["id"] for clip in public_manifest["clips"]] == ["approved"]
    assert public_manifest["clips"][0]["ais_context"]["lat"] == 47.606
    assert public_manifest["clips"][0]["ais_context"]["lon"] == -122.371
    assert "private_s3_key" not in rendered
    assert "receiver_id" not in rendered
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


def test_public_manifest_rejects_bad_ais_tracks() -> None:
    with pytest.raises(PublicExportError, match="ais_tracks"):
        sanitize_public_manifest({"ais_tracks": [{"track_id": "bad", "points": "not-a-list"}]})
